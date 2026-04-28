from __future__ import annotations

import logging
from math import radians, sin, cos, sqrt, atan2
from typing import Any, Dict, List, Optional

import httpx

from src.common.configs.settings import settings

logger = logging.getLogger(__name__)


class GooglePlacesClient:
    """Client for Google Places API (New) — global coverage with exact coordinates."""

    BASE_URL = 'https://places.googleapis.com/v1/places'

    # Map Google types → internal categories
    _TYPE_MAP: Dict[str, str] = {
        'museum': 'museum',
        'art_gallery': 'museum',
        'park': 'park',
        'national_park': 'nature',
        'restaurant': 'restaurant',
        'cafe': 'cafe',
        'church': 'religious',
        'hindu_temple': 'religious',
        'mosque': 'religious',
        'synagogue': 'religious',
        'amusement_park': 'entertainment',
        'zoo': 'entertainment',
        'aquarium': 'entertainment',
        'movie_theater': 'entertainment',
        'night_club': 'nightlife',
        'shopping_mall': 'shopping',
        'tourist_attraction': 'landmark',
        'historical_landmark': 'landmark',
        'cultural_landmark': 'landmark',
        'performing_arts_theater': 'entertainment',
        'beach': 'beach',
        'observation_deck': 'viewpoint',
        'botanical_garden': 'park',
        'city_hall': 'landmark',
        'library': 'landmark',
        'university': 'landmark',
        'stadium': 'entertainment',
        'market': 'shopping',
    }

    INTEREST_QUERIES: Dict[str, str] = {
        'музеи': 'museums',
        'галереи': 'art galleries',
        'достопримечательности': 'tourist attractions landmarks',
        'архитектура': 'architecture landmarks',
        'парки': 'parks gardens',
        'рестораны': 'restaurants',
        'кафе': 'cafes',
        'храмы': 'churches temples',
        'соборы': 'cathedrals',
        'церкви': 'churches',
        'мечети': 'mosques',
        'театры': 'theaters',
        'развлечения': 'entertainment amusement',
        'магазины': 'shopping malls markets',
        'природа': 'nature parks',
        'пляжи': 'beaches',
        'смотровые площадки': 'observation viewpoints',
        'набережные': 'waterfront promenade',
        'ночная жизнь': 'nightlife bars clubs',
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.google_places_api_key
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
        if not self.api_key:
            return []

        queries = self._build_queries(city, interests, num_places)
        all_places: List[Dict[str, Any]] = []
        seen: set = set()

        for query, limit in queries:
            try:
                items = await self._text_search(query, limit)
                for item in items:
                    place_id = item.get('id', '')
                    if place_id and place_id not in seen:
                        seen.add(place_id)
                        place = self._parse_place(item)
                        if place:
                            all_places.append(place)
            except Exception as e:
                logger.warning('Google Places query "%s" failed: %s', query, e)
                continue

        all_places = self._deduplicate_by_proximity(all_places)
        all_places.sort(key=lambda p: p.get('rating') or 0, reverse=True)
        return all_places[:num_places]

    def _build_queries(
        self, city: str, interests: List[str], num_places: int,
    ) -> List[tuple]:
        search_terms: List[str] = []
        matched = set()

        for interest in interests:
            key = interest.lower().strip()
            if key in self.INTEREST_QUERIES:
                term = self.INTEREST_QUERIES[key]
                if term not in matched:
                    search_terms.append(term)
                    matched.add(term)
            elif key not in matched:
                search_terms.append(key)
                matched.add(key)

        if not search_terms:
            search_terms = ['tourist attractions', 'museums', 'parks']

        per_query = max(5, num_places // len(search_terms))
        per_query = min(per_query, 20)  # Google API max is 20 per request

        queries = [(f'{term} in {city}', per_query) for term in search_terms]

        total_capacity = per_query * len(search_terms)
        if total_capacity < num_places:
            extra = min(20, num_places - total_capacity)
            queries.append((f'things to do in {city}', extra))

        return queries

    async def _text_search(self, query: str, max_results: int = 20) -> List[Dict]:
        client = await self._get_client()

        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': self.api_key,
            'X-Goog-FieldMask': (
                'places.id,places.displayName,places.location,'
                'places.types,places.rating,places.userRatingCount,'
                'places.formattedAddress,places.priceLevel,'
                'places.regularOpeningHours'
            ),
        }

        payload = {
            'textQuery': query,
            'maxResultCount': min(max_results, 20),
            'languageCode': 'ru',
        }

        response = await client.post(
            f'{self.BASE_URL}:searchText',
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        places = data.get('places', [])
        logger.info('Google Places "%s": %d results', query, len(places))
        return places

    def _parse_place(self, item: Dict) -> Optional[Dict[str, Any]]:
        location = item.get('location', {})
        lat = location.get('latitude')
        lon = location.get('longitude')
        if lat is None or lon is None:
            return None

        display_name = item.get('displayName', {})
        name = display_name.get('text', '').strip()
        if not name:
            return None

        types = item.get('types', [])
        category = self._classify_category(types)

        rating = item.get('rating')

        price_map = {
            'PRICE_LEVEL_FREE': 1,
            'PRICE_LEVEL_INEXPENSIVE': 2,
            'PRICE_LEVEL_MODERATE': 3,
            'PRICE_LEVEL_EXPENSIVE': 4,
            'PRICE_LEVEL_VERY_EXPENSIVE': 5,
        }
        price_level_str = item.get('priceLevel', '')
        price_level = price_map.get(price_level_str)

        address = item.get('formattedAddress', '')

        return {
            'name': name,
            'lat': float(lat),
            'lon': float(lon),
            'category': category,
            'rating': float(rating) if rating is not None else None,
            'address': address,
            'rubrics': [t.replace('_', ' ') for t in types[:5]],
            'price_level': price_level,
            'opening_hours': self._format_opening_hours(item.get('regularOpeningHours')),
        }

    @staticmethod
    def _format_opening_hours(reg: Any) -> Optional[str]:
        """Convert Google ``regularOpeningHours`` object into ``HH:MM-HH:MM``."""
        if not isinstance(reg, dict):
            return None
        periods = reg.get('periods') or []
        for p in periods:
            open_p = p.get('open') or {}
            close_p = p.get('close') or {}
            oh, om = open_p.get('hour'), open_p.get('minute', 0)
            ch, cm = close_p.get('hour'), close_p.get('minute', 0)
            if oh is None:
                continue
            if ch is None:
                return '00:00-23:59'
            return f'{int(oh):02d}:{int(om or 0):02d}-{int(ch):02d}:{int(cm or 0):02d}'
        return None

    def _classify_category(self, types: List[str]) -> str:
        for t in types:
            if t in self._TYPE_MAP:
                return self._TYPE_MAP[t]
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
