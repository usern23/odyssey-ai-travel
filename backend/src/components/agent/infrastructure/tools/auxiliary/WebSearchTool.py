from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from math import radians, sin, cos, sqrt, atan2
from typing import Any, Dict, List, Optional, Tuple
import httpx
from sqlalchemy import select
from src.common.configs.settings import settings
from src.infrastructure.db.session import async_session_factory
logger = logging.getLogger(__name__)


# TTL for persistent web_search cache entries (24h).
WEB_SEARCH_CACHE_TTL = timedelta(hours=24)


# Hard geo-filter radius around the city centre. Anything further away
# (e.g. POIs from other regions) is dropped before returning places.
CITY_GEO_RADIUS_KM = 30.0

# Minimum POIs that a primary/fallback source must return before we skip
# activating the next fallback in the chain.
MIN_PLACES_BEFORE_FALLBACK = 15

# Country codes where 2GIS offers solid coverage. Outside of this set we
# prefer Google Places as the primary POI source.
TWOGIS_COUNTRIES = {'ru', 'by', 'kz', 'kg', 'uz', 'az'}

NON_TOURIST_DENY_KEYWORDS = [
    # Medical / hospitals
    'медицин', 'клиник', 'больниц', 'поликлиник', 'стоматолог', 'роддом',
    'перинаталь', 'аптек', 'hospital', 'clinic', 'medical center', 'medical centre',
    # Education / admin
    'университет', 'институт', 'колледж', 'школа', 'лицей', 'гимнази',
    'детский сад', 'academy', 'university', 'college', 'school',
    'администрац', 'налогов', 'мфц', 'passport office', 'city hall',
    # Offices / utilities / service points
    'бизнес-центр', 'офис', 'склад', 'логистическ', 'service center',
    'сервисный центр', 'автосервис', 'автосалон', 'шиномонтаж', 'азс',
]


class WebSearchTool:
    MODEL_GPT4 = 'gpt-4.1'
    MODEL_GPT4_MINI = 'gpt-4.1-mini'
    MODEL_SONAR = 'sonar'
    MODEL_SONAR_PRO = 'sonar-pro'

    # Models that accept the OpenAI-style ``web_search_options`` payload
    # (live browsing). Anything outside this set will be sent as a plain
    # chat completion — important on aitunnel where most cheap models
    # don't support web_search_preview.
    WEB_SEARCH_CAPABLE_MODELS = {
        MODEL_GPT4, MODEL_GPT4_MINI, MODEL_SONAR, MODEL_SONAR_PRO,
    }

    # Sensible defaults for ``visit_duration_min`` per category. When a
    # POI already has a recognisable category we skip the LLM enrichment
    # call and use the table below — this saves ~1 LLM round-trip per
    # ~40 places (the dominant cost in WebSearchTool.search_places).
    DEFAULT_DURATION_BY_CATEGORY: Dict[str, int] = {
        'museum': 120,
        'landmark': 45,
        'park': 60,
        'restaurant': 90,
        'cafe': 60,
        'religious': 30,
        'entertainment': 90,
        'shopping': 60,
        'nature': 90,
        'viewpoint': 30,
        'beach': 120,
        'hotel': 0,
        'other': 60,
    }
    DEFAULT_PRICE_BY_CATEGORY: Dict[str, int] = {
        'museum': 3,
        'landmark': 1,
        'park': 1,
        'restaurant': 3,
        'cafe': 2,
        'religious': 1,
        'entertainment': 3,
        'shopping': 3,
        'nature': 1,
        'viewpoint': 1,
        'beach': 1,
        'hotel': 4,
        'other': 2,
    }

    def __init__(
            self,
            api_key: Optional[str] = None,
            base_url: str = 'https://api.aitunnel.ru/v1',
            model: Optional[str] = None,
            search_context_size: str = 'medium'):
        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url
        # Default to whatever is configured for the agent (cheap model
        # like gpt-5.4-nano on aitunnel) instead of hard-coding gpt-4.1.
        self.model = (
            model
            or settings.web_search_model
            or settings.llm_model
            or self.MODEL_GPT4_MINI
        )
        self.search_context_size = search_context_size
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'},
                timeout=60.0)
        return self._client

    async def search(self, query: str,
                     system_prompt: Optional[str] = None) -> Dict[str, Any]:
        if not self.api_key:
            logger.error('No API key configured for web search')
            return {
                'success': False,
                'error': 'API key not configured',
                'content': '',
                'citations': []}

        # Try DB cache first (24h TTL). Cache key also includes system_prompt
        # because different prompts produce different outputs for the same query.
        cache_key = self._build_cache_key(query, system_prompt)
        cached = await self._load_from_cache(cache_key)
        if cached is not None:
            logger.info('web_search cache hit for query: %s', query[:60])
            return cached

        client = await self._get_client()
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': query})
        payload: Dict[str, Any] = {
            'model': self.model,
            'messages': messages,
            'max_tokens': 4096,
        }
        # Only attach web_search_options for models that actually support
        # live browsing on aitunnel — otherwise the API rejects the call.
        if self.model in self.WEB_SEARCH_CAPABLE_MODELS:
            payload['web_search_options'] = {
                'search_context_size': self.search_context_size,
            }
        try:
            response = await client.post('/chat/completions', json=payload)
            response.raise_for_status()
            data = response.json()
            choice = data.get('choices', [{}])[0]
            message = choice.get('message', {})
            content = message.get('content', '')
            annotations = message.get('annotations', [])
            citations = []
            for ann in annotations:
                if ann.get('type') == 'url_citation':
                    citation = ann.get('url_citation', {})
                    citations.append({'url': citation.get('url'), 'title': citation.get(
                        'title'), 'content': citation.get('content')})
            logger.info(
                f'Web search completed: {len(citations)} citations found')
            result = {
                'success': True,
                'content': content,
                'citations': citations}
            await self._store_in_cache(cache_key, query, content, citations)
            return result
        except httpx.HTTPStatusError as e:
            logger.error(
                f'Web search HTTP error: {e.response.status_code} - {e.response.text}')
            return {
                'success': False,
                'error': f'HTTP {e.response.status_code}: {e.response.text}',
                'content': '',
                'citations': []}
        except Exception as e:
            logger.error(f'Web search error: {e}')
            return {
                'success': False,
                'error': str(e),
                'content': '',
                'citations': []}

    # ── Persistent cache helpers ────────────────────────────────────────
    def _build_cache_key(self, query: str, system_prompt: Optional[str]) -> str:
        raw = '|'.join([
            self.model or '',
            self.search_context_size or '',
            system_prompt or '',
            query or '',
        ]).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()

    async def _load_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        try:
            from src.components.agent.infrastructure.models import WebSearchCache

            async with async_session_factory() as session:
                row = await session.execute(
                    select(WebSearchCache).where(
                        WebSearchCache.query_hash == cache_key
                    )
                )
                entry = row.scalar_one_or_none()
                if entry is None:
                    return None
                expires_at = entry.created_at + WEB_SEARCH_CACHE_TTL
                now = datetime.now(timezone.utc)
                # `created_at` is stored with timezone; normalise just in case.
                if entry.created_at.tzinfo is None:
                    expires_at = entry.created_at.replace(tzinfo=timezone.utc) + WEB_SEARCH_CACHE_TTL
                if expires_at < now:
                    return None
                return {
                    'success': True,
                    'content': entry.content,
                    'citations': list(entry.citations or []),
                    'cached': True,
                }
        except Exception as exc:
            logger.warning('web_search cache read failed: %s', exc)
            return None

    async def _store_in_cache(
        self,
        cache_key: str,
        query: str,
        content: str,
        citations: List[Dict[str, Any]],
    ) -> None:
        try:
            from src.components.agent.infrastructure.models import WebSearchCache

            async with async_session_factory() as session:
                existing = await session.execute(
                    select(WebSearchCache).where(
                        WebSearchCache.query_hash == cache_key
                    )
                )
                entry = existing.scalar_one_or_none()
                if entry is not None:
                    entry.content = content
                    entry.citations = citations
                    entry.created_at = datetime.now(timezone.utc)
                else:
                    session.add(
                        WebSearchCache(
                            query_hash=cache_key,
                            query=query[:8000],
                            model=self.model or '',
                            search_context_size=self.search_context_size or 'medium',
                            content=content,
                            citations=citations,
                        )
                    )
                await session.commit()
        except Exception as exc:
            logger.warning('web_search cache write failed: %s', exc)

    async def search_places(self,
                            city: str,
                            interests: List[str],
                            num_places: int = 50) -> Dict[str, Any]:
        """Find touristic POIs for a city.

        Source chain depends on the city's country:
          * RU/CIS countries: 2GIS → Overpass → Google → LLM
          * Other countries : Google → Overpass → LLM
        After aggregation every place is hard-filtered by distance from the
        city centre (CITY_GEO_RADIUS_KM) to avoid cross-region hallucinations.
        """
        center, country = await self._resolve_city_center_and_country(city)
        use_2gis_primary = (country or '').lower() in TWOGIS_COUNTRIES or country is None
        aggregated: List[Dict[str, Any]] = []
        source_labels: List[str] = []

        def current_count() -> int:
            return self._count_within_radius(aggregated, center)

        # Push the primary source harder before falling back to OSM
        # noise. Old value (num_places // 2) tripped Overpass too eagerly
        # for mid-size cities like Omsk and let low-quality landmarks
        # dilute 2GIS results.
        target_before_fallback = min(num_places, max(MIN_PLACES_BEFORE_FALLBACK, 50))

        # ── 1. Primary source depending on country ──────────────────────
        if use_2gis_primary and settings.geo_api_key:
            try:
                from src.components.agent.infrastructure.tools.auxiliary.TwoGisClient import TwoGisClient
                twogis = TwoGisClient()
                raw_places = await twogis.search_places(city, interests, num_places)
                for p in raw_places:
                    p['source'] = '2gis'
                aggregated.extend(raw_places)
                if raw_places:
                    source_labels.append('2gis')
                await twogis.close()
            except Exception as e:
                logger.warning('2GIS search failed: %s', e)

        if (not use_2gis_primary or current_count() < target_before_fallback) and settings.google_places_api_key:
            try:
                from src.components.agent.infrastructure.tools.auxiliary.GooglePlacesClient import GooglePlacesClient
                gplaces = GooglePlacesClient()
                google_places = await gplaces.search_places(city, interests, num_places)
                for p in google_places:
                    p['source'] = 'google'
                aggregated.extend(google_places)
                if google_places:
                    source_labels.append('google')
                await gplaces.close()
            except Exception as e:
                logger.warning('Google Places search failed: %s', e)

        # ── 2. Overpass fallback (if we still need more) ────────────────
        if center and current_count() < target_before_fallback:
            try:
                from src.components.agent.infrastructure.tools.auxiliary.OverpassClient import OverpassClient
                overpass = OverpassClient()
                overpass_places = await overpass.search_places(
                    center_lat=center[0],
                    center_lon=center[1],
                    radius_m=int(CITY_GEO_RADIUS_KM * 1000),
                    num_places=num_places,
                )
                for p in overpass_places:
                    p['source'] = 'overpass'
                aggregated.extend(overpass_places)
                if overpass_places:
                    source_labels.append('overpass')
                await overpass.close()
            except Exception as e:
                logger.warning('Overpass fallback failed: %s', e)

        # ── 3. LLM last-resort fallback with strict geo context ─────────
        if current_count() < MIN_PLACES_BEFORE_FALLBACK:
            llm_places = await self._llm_fallback_places(
                city=city,
                interests=interests,
                num_places=num_places,
                center=center,
            )
            for p in llm_places:
                p['source'] = 'llm'
            aggregated.extend(llm_places)
            if llm_places:
                source_labels.append('llm')

        # ── Hard geo-filter + enrichment ────────────────────────────────
        filtered = self._apply_geo_filter(aggregated, center)
        # Deduplicate by proximity across sources (50 m threshold).
        filtered = self._deduplicate_by_proximity(filtered)
        # Remove obvious non-tourist/service POIs regardless of source.
        filtered = self._filter_non_tourist_places(filtered)

        # Apply category-based defaults BEFORE any LLM enrichment. This
        # is the single biggest cost-saver: 2GIS / Google / Overpass
        # already give us a category for every POI, so for the bulk of
        # places we can skip the LLM round-trip entirely.
        for p in filtered:
            cat = (p.get('category') or 'other').lower()
            if 'visit_duration_min' not in p:
                p['visit_duration_min'] = self.DEFAULT_DURATION_BY_CATEGORY.get(
                    cat, self.DEFAULT_DURATION_BY_CATEGORY['other'])
            if p.get('price_level') is None:
                p['price_level'] = self.DEFAULT_PRICE_BY_CATEGORY.get(
                    cat, self.DEFAULT_PRICE_BY_CATEGORY['other'])
            p.setdefault('description', '')

        # Only call the LLM enrichment for places that still lack a
        # description AND have an unknown / generic category. After the
        # default pass above this is usually 0 or a small minority.
        needs_enrichment = [
            p for p in filtered
            if not p.get('description')
            and (p.get('category') or 'other').lower() == 'other'
        ]
        if needs_enrichment:
            try:
                await self._enrich_places_with_llm(needs_enrichment, city)
            except Exception as e:
                logger.warning('Enrichment failed: %s', e)

        if not filtered:
            return {
                'success': False,
                'places': [],
                'error': 'No places found for city within %.0f km radius' % CITY_GEO_RADIUS_KM,
                'raw_content': '',
                'citations': [],
                'source': '+'.join(source_labels) or 'none',
            }

        # Sort: rated entries first (real reviews from 2GIS/Google),
        # synthetic-rated OSM entries next, unrated last. Within each
        # bucket fall back to (rating, _priority) descending. This
        # guarantees a 2GIS museum with rating 3.8 ranks above an
        # Overpass viewpoint with synthetic 4.0.
        def _sort_key(p: Dict[str, Any]) -> tuple:
            has_real_rating = (
                p.get('rating') is not None
                and not p.get('rating_synthetic')
            )
            has_any_rating = p.get('rating') is not None
            return (
                1 if has_real_rating else 0,
                1 if has_any_rating else 0,
                p.get('rating') or 0.0,
                p.get('_priority') or 0,
            )

        filtered.sort(key=_sort_key, reverse=True)
        trimmed = filtered[:num_places]

        logger.info(
            'search_places[%s]: %d places (sources: %s, geo-filtered from %d)',
            city, len(trimmed), '+'.join(source_labels), len(aggregated),
        )
        return {
            'success': True,
            'places': trimmed,
            'raw_content': f"aggregated from {'+'.join(source_labels)}: {len(trimmed)} places",
            'citations': [],
            'source': '+'.join(source_labels) or 'none',
        }

    # ------------------------------------------------------------------
    # Geo helpers
    # ------------------------------------------------------------------

    async def _resolve_city_center(self, city: str) -> Optional[Tuple[float, float]]:
        center, _ = await self._resolve_city_center_and_country(city)
        return center

    async def _resolve_city_center_and_country(
        self, city: str,
    ) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
        """Resolve the city's centre coordinates AND ISO country code.

        Uses OpenStreetMap Nominatim (no key) as the source of truth for
        country detection; falls back to 2GIS geocode for coordinates when
        Nominatim is unreachable. The returned country code is lowercase
        ISO-3166 alpha-2 (e.g. ``ru``, ``fr``).
        """
        center: Optional[Tuple[float, float]] = None
        country: Optional[str] = None
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                headers={'User-Agent': 'odyssey-ai-travel/1.0'},
            ) as client:
                resp = await client.get(
                    'https://nominatim.openstreetmap.org/search',
                    params={'q': city, 'format': 'json', 'limit': 1, 'addressdetails': 1},
                )
                resp.raise_for_status()
                items = resp.json() or []
                if items:
                    first = items[0]
                    lat = first.get('lat')
                    lon = first.get('lon')
                    if lat and lon:
                        center = (float(lat), float(lon))
                    addr = first.get('address') or {}
                    country = (addr.get('country_code') or '').lower() or None
        except Exception as e:
            logger.warning('Nominatim country lookup failed for "%s": %s', city, e)

        if center is None and settings.geo_api_key:
            try:
                from src.components.agent.infrastructure.tools.auxiliary.TwoGisClient import TwoGisClient
                twogis = TwoGisClient()
                center = await twogis.geocode(city)
                await twogis.close()
                # 2GIS reachable only for RU/CIS; mark country as ru if unknown.
                if center and not country:
                    country = 'ru'
            except Exception as e:
                logger.warning('Failed to geocode city "%s" via 2GIS: %s', city, e)

        return center, country

    def _apply_geo_filter(
        self,
        places: List[Dict[str, Any]],
        center: Optional[Tuple[float, float]],
    ) -> List[Dict[str, Any]]:
        if not center:
            return places
        c_lat, c_lon = center
        radius_m = CITY_GEO_RADIUS_KM * 1000
        filtered: List[Dict[str, Any]] = []
        dropped = 0
        for p in places:
            try:
                dist = self._haversine_m(c_lat, c_lon, p['lat'], p['lon'])
            except (KeyError, TypeError):
                dropped += 1
                continue
            if dist <= radius_m:
                filtered.append(p)
            else:
                dropped += 1
        if dropped:
            logger.info('Geo-filter dropped %d places outside %.0f km', dropped, CITY_GEO_RADIUS_KM)
        return filtered

    def _count_within_radius(
        self,
        places: List[Dict[str, Any]],
        center: Optional[Tuple[float, float]],
    ) -> int:
        if not center:
            return len(places)
        c_lat, c_lon = center
        radius_m = CITY_GEO_RADIUS_KM * 1000
        return sum(
            1 for p in places
            if 'lat' in p and 'lon' in p
            and self._haversine_m(c_lat, c_lon, p['lat'], p['lon']) <= radius_m
        )

    def _deduplicate_by_proximity(
        self,
        places: List[Dict[str, Any]],
        threshold_m: float = 50.0,
    ) -> List[Dict[str, Any]]:
        unique: List[Dict[str, Any]] = []
        for place in places:
            is_dup = False
            for i, existing in enumerate(unique):
                try:
                    dist = self._haversine_m(
                        place['lat'], place['lon'],
                        existing['lat'], existing['lon'],
                    )
                except (KeyError, TypeError):
                    continue
                if dist < threshold_m:
                    if (place.get('rating') or 0) > (existing.get('rating') or 0):
                        unique[i] = place
                    is_dup = True
                    break
            if not is_dup:
                unique.append(place)
        return unique

    def _filter_non_tourist_places(
        self,
        places: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        tourist_categories = {
            'museum', 'landmark', 'park', 'religious', 'entertainment',
            'nature', 'viewpoint', 'beach', 'cafe', 'restaurant', 'nightlife',
        }
        filtered: List[Dict[str, Any]] = []
        removed = 0
        for p in places:
            category = (p.get('category') or '').lower()
            text = ' '.join([
                str(p.get('name') or ''),
                str(p.get('address') or ''),
                str(p.get('description') or ''),
                ' '.join(str(x) for x in (p.get('rubrics') or [])),
            ]).lower()
            if any(keyword in text for keyword in NON_TOURIST_DENY_KEYWORDS):
                removed += 1
                continue
            if category not in tourist_categories and category not in {'shopping'}:
                removed += 1
                continue
            filtered.append(p)
        if removed:
            logger.info('Non-tourist filter removed %d places after aggregation', removed)
        return filtered

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6_371_000
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return R * 2 * atan2(sqrt(a), sqrt(1 - a))

    # ------------------------------------------------------------------
    # LLM last-resort fallback (with geo binding)
    # ------------------------------------------------------------------

    async def _llm_fallback_places(
        self,
        city: str,
        interests: List[str],
        num_places: int,
        center: Optional[Tuple[float, float]],
    ) -> List[Dict[str, Any]]:
        interests_str = ', '.join(interests) if interests else 'достопримечательности'
        geo_hint = ''
        if center:
            lat, lon = center
            geo_hint = (
                f'\n\nКРИТИЧНО: все места должны находиться в радиусе {CITY_GEO_RADIUS_KM:.0f} км '
                f'от центра города ({lat:.4f}, {lon:.4f}). '
                f'НЕ включай достопримечательности других городов, регионов или природных объектов '
                f'за пределами этого радиуса. Координаты каждого места проверь.'
            )
        query = (
            f'Найди {num_places} лучших туристических мест в городе {city}.\n'
            f'Интересы: {interests_str}.{geo_hint}\n\n'
            'Для КАЖДОГО места укажи: name, lat, lon, category '
            '(museum/landmark/park/restaurant/cafe/religious/entertainment/shopping/nature/viewpoint/beach), '
            'visit_duration_min, rating (0.0-5.0), price_level (1-5), description, '
            'opening_hours в формате "HH:MM-HH:MM" или "24/7".\n'
            'Ответ строго JSON-массивом без комментариев.'
        )
        system_prompt = (
            'Ты эксперт по туризму. Возвращай только реальные места с проверенными координатами. '
            'Если объект находится вне указанной области — НЕ включай его. '
            'Никаких выдуманных мест и координат. Отвечай только JSON массивом.'
        )
        result = await self.search(query, system_prompt)
        if not result.get('success'):
            return []
        return self._parse_places_from_response(result.get('content', ''))

    async def _enrich_places_with_llm(
        self,
        places: List[Dict[str, Any]],
        city: str,
    ) -> List[Dict[str, Any]]:
        """Use LLM to add visit_duration_min, price_level, and description."""
        BATCH_SIZE = 40
        for batch_start in range(0, len(places), BATCH_SIZE):
            batch = places[batch_start:batch_start + BATCH_SIZE]
            try:
                await self._enrich_batch(batch, city)
            except Exception as e:
                logger.warning('LLM enrichment failed for batch %d: %s', batch_start, e)
                for p in batch:
                    p.setdefault('visit_duration_min', 60)
                    p.setdefault('price_level', 2)
                    p.setdefault('description', '')
        return places

    async def _enrich_batch(
        self, batch: List[Dict[str, Any]], city: str,
    ) -> None:
        lines = []
        for i, p in enumerate(batch):
            rubrics_str = ', '.join(p.get('rubrics', [])) or p.get('category', '')
            addr = p.get('address', '')
            lines.append(f"{i + 1}. {p['name']} ({rubrics_str}) — {addr}")

        places_text = '\n'.join(lines)

        query = (
            f'Для каждого из {len(batch)} мест в городе {city} определи:\n'
            '1. visit_duration_min — рекомендуемое время посещения в минутах\n'
            '2. price_level — уровень цен (1=бесплатно, 2=дёшево, 3=средне, 4=дорого, 5=очень дорого)\n'
            '3. description — краткое описание на русском (1-2 предложения)\n\n'
            f'Места:\n{places_text}\n\n'
            'Ответь ТОЛЬКО JSON массивом:\n'
            '[{"index": 1, "visit_duration_min": 180, "price_level": 4, "description": "..."}]'
        )
        system_prompt = (
            'Ты эксперт по туризму. Для каждого места укажи реалистичное время посещения, '
            'уровень цен и описание. Отвечай ТОЛЬКО JSON массивом.'
        )

        result = await self.search(query, system_prompt)
        if not result['success']:
            raise RuntimeError(result.get('error', 'LLM enrichment failed'))

        enrichments = self._parse_enrichments(result['content'])
        for enr in enrichments:
            idx = enr.get('index', 0) - 1
            if 0 <= idx < len(batch):
                batch[idx]['visit_duration_min'] = int(enr.get('visit_duration_min', 60))
                batch[idx]['price_level'] = int(enr.get('price_level', 2))
                batch[idx]['description'] = enr.get('description', '')

        # Fill defaults for any unenriched places
        for p in batch:
            p.setdefault('visit_duration_min', 60)
            p.setdefault('price_level', 2)
            p.setdefault('description', '')

    def _parse_enrichments(self, content: str) -> List[Dict[str, Any]]:
        import json
        import re
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', content)
            if json_match:
                json_str = json_match.group(0)
            else:
                return []
        try:
            data = json.loads(json_str)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError as e:
            logger.error('Failed to parse enrichment JSON: %s', e)
            return []

    def _parse_places_from_response(
            self, content: str) -> List[Dict[str, Any]]:
        import json
        import re
        json_match = re.search('```json\\s*([\\s\\S]*?)\\s*```', content)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search('\\[\\s*\\{[\\s\\S]*\\}\\s*\\]', content)
            if json_match:
                json_str = json_match.group(0)
            else:
                logger.warning('Could not find JSON in web search response')
                return []
        try:
            places = json.loads(json_str)
            if isinstance(places, list):
                valid_places = []
                for p in places:
                    if all((k in p for k in ['name', 'lat', 'lon'])):
                        valid_places.append(
                            {
                                'name': p.get('name'), 'lat': float(
                                    p.get('lat')), 'lon': float(
                                    p.get('lon')), 'category': p.get(
                                    'category', 'other'), 'visit_duration_min': int(
                                    p.get(
                                        'visit_duration_min', 60)),
                                'rating': float(p['rating']) if p.get('rating') is not None else None,
                                'price_level': int(p['price_level']) if p.get('price_level') is not None else None,
                                'description': p.get('description'),
                                'opening_hours': p.get('opening_hours')})
                return valid_places
        except json.JSONDecodeError as e:
            logger.error(f'Failed to parse places JSON: {e}')
        return []

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
