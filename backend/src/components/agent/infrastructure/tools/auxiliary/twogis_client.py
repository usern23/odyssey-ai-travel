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

        # Sort by rating (highest first) before trimming
        all_places.sort(key=lambda p: p.get('rating') or 0, reverse=True)
        return all_places[:num_places]

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
                'fields': 'items.point,items.rubrics,items.reviews,items.description',
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
        }

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

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
