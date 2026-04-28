from __future__ import annotations

import logging
from math import radians, sin, cos, sqrt, atan2
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.common.configs.settings import settings

logger = logging.getLogger(__name__)


class TwoGisClient:
    """Client for 2GIS Catalog API — real places with exact coordinates and ratings."""

    MAX_PAGE_SIZE = 10
    CITY_RADIUS_KM = 30.0

    INTEREST_QUERIES: Dict[str, List[str]] = {
        'музеи': ['музей'],
        'галереи': ['галерея'],
        'достопримечательности': ['достопримечательность'],
        'архитектура': ['памятник архитектуры'],
        'парки': ['парк'],
        'скверы': ['сквер'],
        'рестораны': ['ресторан'],
        'кафе': ['кафе'],
        'кофейни': ['кофейня'],
        'храмы': ['храм'],
        'соборы': ['собор'],
        'церкви': ['церковь'],
        'мечети': ['мечеть'],
        'театры': ['театр'],
        'развлечения': ['развлекательный центр'],
        'магазины': ['торговый центр'],
        'природа': ['природный парк'],
        'пляжи': ['пляж'],
        'смотровые площадки': ['смотровая площадка'],
        'зоопарки': ['зоопарк'],
        'аквапарки': ['аквапарк'],
        'набережные': ['набережная'],
    }

    # Priority-ordered: religious before cafe (e.g. "Казанский кафедральный собор")
    _RUBRIC_KEYWORDS: List[tuple] = [
        ('храм', 'religious'),
        ('собор', 'religious'),
        ('церков', 'religious'),
        ('мечет', 'religious'),
        ('монастыр', 'religious'),
        ('часовн', 'religious'),
        ('синагог', 'religious'),
        ('кафедральн', 'religious'),
        ('музе', 'museum'),
        ('галере', 'museum'),
        ('выставочн', 'museum'),
        ('экспозиц', 'museum'),
        ('памятник', 'landmark'),
        ('достоприм', 'landmark'),
        ('историч', 'landmark'),
        ('крепост', 'landmark'),
        ('дворец', 'landmark'),
        ('замок', 'landmark'),
        ('башн', 'landmark'),
        ('ворот', 'landmark'),
        ('мост', 'landmark'),
        ('фонтан', 'landmark'),
        ('площад', 'landmark'),
        ('набережн', 'landmark'),
        ('парк', 'park'),
        ('сквер', 'park'),
        ('ботаническ', 'park'),
        ('театр', 'entertainment'),
        ('кинотеатр', 'entertainment'),
        ('развлеч', 'entertainment'),
        ('цирк', 'entertainment'),
        ('зоопарк', 'entertainment'),
        ('аквапарк', 'entertainment'),
        ('планетари', 'entertainment'),
        ('концертн', 'entertainment'),
        ('филармон', 'entertainment'),
        ('ресторан', 'restaurant'),
        ('кафе', 'cafe'),
        ('кофейн', 'cafe'),
        ('кондитерск', 'cafe'),
        ('торгов', 'shopping'),
        ('магазин', 'shopping'),
        ('рынок', 'shopping'),
        ('заповед', 'nature'),
        ('природ', 'nature'),
        ('пляж', 'beach'),
        ('смотров', 'viewpoint'),
        ('обзорн', 'viewpoint'),
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or settings.geo_api_key
        self.base_url = base_url or settings.geocoder_base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def search_places(
        self,
        city: str,
        interests: List[str],
        num_places: int = 50,
    ) -> List[Dict[str, Any]]:
        """Search for real places via 2GIS Catalog API.

        Returns places with exact coordinates and ratings but WITHOUT
        visit_duration_min and description (use LLM enrichment for those).
        """
        if not self.api_key:
            return []

        queries = self._build_queries(city, interests, num_places)

        all_places: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for query, limit in queries:
            try:
                items = await self._api_search(query, limit)
                for item in items:
                    item_id = item.get('id')
                    if item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        place = self._parse_item(item)
                        if place:
                            all_places.append(place)
            except Exception as e:
                logger.warning('2GIS query "%s" failed: %s', query, e)
                continue

        all_places = self._deduplicate_by_proximity(all_places)
        all_places = await self._filter_city_scope(city, all_places)
        all_places = self._filter_noise_places(all_places)

        # Sort by rating (highest first) before trimming
        all_places.sort(key=lambda p: p.get('rating') or 0, reverse=True)
        return all_places[:num_places]

    async def geocode(self, query: str) -> Optional[Tuple[float, float]]:
        """Resolve free-form address/place to coordinates via 2GIS catalog search."""
        if not self.api_key:
            return None
        try:
            items = await self._api_search(query, num_results=1)
            if not items:
                return None
            point = items[0].get('point') or {}
            lat = point.get('lat')
            lon = point.get('lon')
            if lat is None or lon is None:
                return None
            return (float(lat), float(lon))
        except Exception as e:
            logger.warning('2GIS geocode failed for "%s": %s', query, e)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_queries(
        self, city: str, interests: List[str], num_places: int,
    ) -> List[tuple]:
        search_terms: List[str] = []
        matched = set()

        for interest in interests:
            key = interest.lower().strip()
            if key in self.INTEREST_QUERIES:
                for term in self.INTEREST_QUERIES[key]:
                    if term not in matched:
                        search_terms.append(term)
                        matched.add(term)
            elif key not in matched:
                search_terms.append(key)
                matched.add(key)

        if not search_terms:
            search_terms = ['достопримечательность', 'музей', 'парк']

        per_query = max(10, num_places // len(search_terms))
        per_query = min(per_query, self.MAX_PAGE_SIZE * 5)  # max 5 pages × 10 items

        queries = [(f'{term} {city}', per_query) for term in search_terms]

        # If the total capacity < num_places, add a generic query
        total_capacity = per_query * len(search_terms)
        if total_capacity < num_places:
            extra = min(self.MAX_PAGE_SIZE, num_places - total_capacity)
            queries.append((f'что посмотреть {city}', extra))

        return queries

    async def _api_search(self, query: str, num_results: int = 10) -> List[Dict]:
        client = await self._get_client()
        all_items: List[Dict] = []
        pages_needed = max(1, (num_results + self.MAX_PAGE_SIZE - 1) // self.MAX_PAGE_SIZE)
        pages_needed = min(pages_needed, 5)  # cap at 5 pages to avoid excessive requests

        for page in range(1, pages_needed + 1):
            params = {
                'key': self.api_key,
                'q': query,
                'page_size': self.MAX_PAGE_SIZE,
                'page': page,
                'fields': 'items.point,items.rubrics,items.reviews,items.description,items.schedule',
                'sort': 'relevance',
            }

            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            result = data.get('result', {})
            items = result.get('items', [])
            total = result.get('total', 0)

            if page == 1:
                logger.info(
                    '2GIS "%s": %d items (total %d, fetching %d pages)',
                    query, len(items), total, pages_needed,
                )

            all_items.extend(items)

            if len(all_items) >= num_results or len(items) < self.MAX_PAGE_SIZE:
                break

        return all_items[:num_results]

    def _parse_item(self, item: Dict) -> Optional[Dict[str, Any]]:
        point = item.get('point')
        if not point:
            return None

        name = item.get('name', '').strip()
        if not name:
            return None

        lat = point.get('lat')
        lon = point.get('lon')
        if lat is None or lon is None:
            return None

        rubrics = item.get('rubrics', [])
        purpose = item.get('purpose_name', '')
        category = self._classify_category(rubrics, name, purpose)

        reviews = item.get('reviews', {})
        rating = reviews.get('general_rating')

        address = item.get('address_name', '')

        return {
            'name': name,
            'lat': float(lat),
            'lon': float(lon),
            'category': category,
            'rating': float(rating) if rating is not None else None,
            'address': address,
            'rubrics': [r.get('name', '') for r in rubrics],
            'opening_hours': self._format_schedule(item.get('schedule')),
        }

    @staticmethod
    def _format_schedule(schedule: Any) -> Optional[str]:
        """Convert 2GIS schedule object into a human-readable ``HH:MM-HH:MM`` string.

        2GIS returns either a dict ``{"Mon": {"working_hours": [{"from": "10:00", "to": "19:00"}]}, ...}``
        or the special key ``Everyday``. We pick the first working window we find
        and return it; the scheduler downstream handles weekly overrides via
        category fallbacks.
        """
        if not schedule or not isinstance(schedule, dict):
            return None
        if schedule.get('is_24x7'):
            return '00:00-23:59'
        day_order = ['Everyday', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        for day in day_order:
            info = schedule.get(day)
            if not isinstance(info, dict):
                continue
            hours = info.get('working_hours') or []
            if hours and isinstance(hours, list):
                first = hours[0]
                if isinstance(first, dict) and first.get('from') and first.get('to'):
                    return f"{first['from']}-{first['to']}"
        return None

    def _classify_category(self, rubrics: List[Dict], name: str, purpose: str = '') -> str:
        # Purpose name from 2GIS is often the most reliable signal
        text = purpose.lower() + ' ' + ' '.join(r.get('name', '').lower() for r in rubrics)
        text += ' ' + name.lower()

        for keyword, cat in self._RUBRIC_KEYWORDS:
            if keyword in text:
                return cat

        return 'landmark'

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6_371_000
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return R * 2 * atan2(sqrt(a), sqrt(1 - a))

    def _deduplicate_by_proximity(
        self, places: List[Dict[str, Any]], threshold_m: float = 50.0,
    ) -> List[Dict[str, Any]]:
        unique: List[Dict[str, Any]] = []
        for place in places:
            is_dup = False
            for i, existing in enumerate(unique):
                dist = self._haversine(
                    place['lat'], place['lon'],
                    existing['lat'], existing['lon'],
                )
                if dist < threshold_m:
                    if (place.get('rating') or 0) > (existing.get('rating') or 0):
                        unique[i] = place
                    is_dup = True
                    break
            if not is_dup:
                unique.append(place)
        return unique

    async def _filter_city_scope(
        self,
        city: str,
        places: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Drop places too far from city center to avoid cross-region artifacts."""
        center = await self.geocode(city)
        if not center:
            return places
        c_lat, c_lon = center
        filtered = [
            p for p in places
            if self._haversine(c_lat, c_lon, p['lat'], p['lon']) <= self.CITY_RADIUS_KM * 1000
        ]
        # Keep original set only if filtering becomes too aggressive.
        return filtered if len(filtered) >= max(8, len(places) // 4) else places

    def _filter_noise_places(self, places: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove technical/service points that are usually irrelevant for travel plans.

        Uses both a blacklist of service-oriented keywords and a whitelist of
        tourist-quality categories. A place must either (a) belong to a
        whitelisted category or (b) have a clean name/rubric set to survive.
        """
        deny_keywords = [
            # Commercial chains / retail
            'лемана', 'леруа', 'мерлен', 'порше', 'porsche', 'трансехсервис',
            'транстехсервис', 'автосалон', 'автоцентр', 'автосервис', 'шиномонтаж',
            'гипермаркет', 'супермаркет', 'минимаркет', 'мини-маркет',
            'продуктовый', 'продукты', 'гастроном', 'дискаунтер',
            'магнит ', 'пятёрочка', 'пятерочка', 'перекрёсток', 'перекресток',
            'дикси', 'ашан', 'metro cash', 'окей',
            'строительных материалов', 'строительный гипермаркет',
            'trc', 'trк', 'тц ', 'тк ', 'торговый центр', 'бизнес-центр',
            'ломбард', 'комиссионный',
            # Medical / pharmacy
            'медицинский центр', 'медцентр', 'стоматолог', 'стоматологическ',
            'поликлиник', 'больниц', 'госпиталь', 'клиник', 'диспансер',
            'аптек', 'оптик', 'оптика', 'офтальмолог',
            'роддом', 'родильный', 'перинатальн', 'травмпункт',
            'ветеринарн', 'ветклиник',
            # Government / public services
            'налоговая', 'фнс ', 'мфц', 'паспортный', 'военкомат',
            'госуслуги', 'пенсионный фонд', 'пфр ', 'росреестр',
            'администрация ', 'мэрия ',
            # Banks / atm
            'банк ', 'банкомат', 'отделение банка', 'sberbank', 'сбербанк',
            'втб ', 'альфа-банк', 'тинькофф', 'росбанк', 'газпромбанк',
            'обмен валют', 'обменник',
            # Education
            'детский сад', 'школа ', 'гимназия', 'лицей',
            'университет ', 'колледж ', 'техникум ', 'академия ',
            'автошкола', 'языковая школа', 'кружок ', 'учебный центр',
            # Auto / fuel / parking
            'автомойка', 'парковка', 'паркинг', 'parking',
            'заправк', 'азс ', 'нефтемагистраль', 'газпромнефть',
            'роснефть', 'лукойл', 'татнефть', 'shell',
            # Offices / industrial
            'офис', 'торгово-офис', 'склад', 'сервисный центр', 'логистический',
            'промышленн', 'производственн', 'индустриальн',
            'юридическ', 'нотариус', 'адвокат',
            # Misc service
            'химчистк', 'прачечн', 'ритуальн', 'похоронн', 'кладбище',
            'крематори', 'фотосалон', 'копировальн', 'типография',
        ]

        tourist_categories = {
            'museum', 'landmark', 'park', 'religious', 'entertainment',
            'nature', 'viewpoint', 'beach', 'cafe', 'restaurant',
        }

        filtered: List[Dict[str, Any]] = []
        for p in places:
            category = (p.get('category') or '').lower()
            text = ' '.join([
                (p.get('name') or ''),
                (p.get('address') or ''),
                ' '.join(p.get('rubrics') or []),
            ]).lower()
            if any(k in text for k in deny_keywords):
                continue
            # Require either a tourist-quality category or a non-empty
            # interesting rubric set. Bare `landmark` without rubric info
            # coming from `_classify_category` fallback still passes because
            # blacklist above handles the common noise.
            if category not in tourist_categories and not p.get('rubrics'):
                continue
            filtered.append(p)

        # Keep the original set only if filtering wipes almost everything.
        return filtered if len(filtered) >= max(8, len(places) // 4) else places

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
