from __future__ import annotations

import logging
from math import radians, sin, cos, sqrt, atan2
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


class OverpassClient:
    """Fallback POI source using OpenStreetMap Overpass API.

    Used when 2GIS returns too few results. Always returns real OSM objects
    with exact coordinates, so no hallucination is possible.
    """

    DEFAULT_ENDPOINT = 'https://overpass-api.de/api/interpreter'
    BACKUP_ENDPOINT = 'https://overpass.kumi.systems/api/interpreter'

    # Whitelist of historic=* values that are actually tourist-relevant.
    # Excludes 'building', 'manor' (often residential), 'yes' (unspecified),
    # and unspecified historic markers near hospitals/schools/etc.
    HISTORIC_WHITELIST = (
        'monument', 'memorial', 'castle', 'fort', 'citadel', 'ruins',
        'archaeological_site', 'tower', 'wayside_shrine', 'wayside_cross',
        'battlefield', 'aqueduct', 'city_gate', 'fortress', 'palace',
    )

    # Tags whose presence on an element marks it as NOT a tourist POI,
    # even if it also has a generic tag like historic=yes.
    EXCLUDE_TAG_VALUES: Dict[str, set] = {
        'amenity': {
            'hospital', 'clinic', 'doctors', 'dentist', 'pharmacy',
            'veterinary', 'school', 'kindergarten', 'college', 'university',
            'language_school', 'driving_school', 'bank', 'atm',
            'bureau_de_change', 'post_office', 'fuel', 'car_wash',
            'car_rental', 'car_sharing', 'fast_food', 'food_court',
            'parking', 'parking_entrance', 'parking_space',
            'bus_station', 'taxi', 'ferry_terminal', 'townhall',
            'courthouse', 'police', 'prison', 'fire_station',
            'embassy', 'social_facility', 'nursing_home', 'childcare',
            'public_bath', 'toilets', 'shower', 'recycling',
            'waste_disposal', 'waste_transfer_station', 'grave_yard',
            'crematorium', 'funeral_hall',
        },
    }

    # If element has ANY of these top-level keys, it's not a tourist POI.
    EXCLUDE_TAG_KEYS = (
        'shop', 'office', 'craft', 'industrial', 'healthcare',
        'emergency', 'man_made',
    )

    # Synthetic rating per priority bucket — used so OSM points without
    # real ratings can still be ranked sensibly against rated 2GIS data.
    _PRIORITY_TO_SYNTH_RATING = {
        10: 4.4,  # museum / gallery
        9: 4.2,   # major historic / attraction
        8: 4.0,   # zoo / theme park / viewpoint
        7: 3.6,   # theatre / religious / cinema
        6: 3.4,   # park / nature / beach
        3: 2.5,   # generic landmark fallback
    }

    # OSM tag -> our category
    _TAG_CATEGORY_MAP: List[tuple] = [
        ('tourism=museum', 'museum'),
        ('tourism=gallery', 'museum'),
        ('tourism=artwork', 'landmark'),
        ('tourism=attraction', 'landmark'),
        ('tourism=viewpoint', 'viewpoint'),
        ('tourism=zoo', 'entertainment'),
        ('tourism=theme_park', 'entertainment'),
        ('tourism=aquarium', 'entertainment'),
        ('historic=monument', 'landmark'),
        ('historic=memorial', 'landmark'),
        ('historic=castle', 'landmark'),
        ('historic=fort', 'landmark'),
        ('historic=ruins', 'landmark'),
        ('historic=archaeological_site', 'landmark'),
        ('historic=church', 'religious'),
        ('leisure=park', 'park'),
        ('leisure=garden', 'park'),
        ('leisure=nature_reserve', 'nature'),
        ('natural=peak', 'viewpoint'),
        ('natural=beach', 'beach'),
        ('amenity=place_of_worship', 'religious'),
        ('amenity=theatre', 'entertainment'),
        ('amenity=cinema', 'entertainment'),
        ('amenity=arts_centre', 'entertainment'),
        ('amenity=planetarium', 'entertainment'),
    ]

    def __init__(self, endpoint: Optional[str] = None, timeout: float = 30.0):
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={'User-Agent': 'odyssey-ai-travel/1.0'},
            )
        return self._client

    async def search_places(
        self,
        center_lat: float,
        center_lon: float,
        radius_m: int = 30_000,
        num_places: int = 60,
    ) -> List[Dict[str, Any]]:
        """Query Overpass for touristic POIs around a center point."""
        query = self._build_query(center_lat, center_lon, radius_m)
        try:
            elements = await self._execute_query(query)
        except Exception as e:
            logger.warning('Overpass query failed on %s: %s', self.endpoint, e)
            if self.endpoint != self.BACKUP_ENDPOINT:
                try:
                    self.endpoint = self.BACKUP_ENDPOINT
                    elements = await self._execute_query(query)
                except Exception as e2:
                    logger.warning('Overpass backup endpoint also failed: %s', e2)
                    return []
            else:
                return []

        raw_places: List[Dict[str, Any]] = []
        for el in elements:
            place = self._parse_element(el)
            if place:
                raw_places.append(place)

        # Deduplicate by proximity (OSM often has node + way for the same object).
        deduped = self._deduplicate(raw_places)
        deduped.sort(key=lambda p: p.get('_priority', 0), reverse=True)
        return deduped[:num_places]

    def _build_query(self, lat: float, lon: float, radius_m: int) -> str:
        around = f'(around:{radius_m},{lat},{lon})'
        # Build a regex-anchored historic whitelist so Overpass itself
        # filters out historic=building, historic=yes, historic=ruins of a
        # collapsed barn, etc., before the response leaves the server.
        historic_re = '|'.join(self.HISTORIC_WHITELIST)
        parts = [
            f'node["tourism"~"^(museum|gallery|attraction|viewpoint|artwork|zoo|theme_park|aquarium)$"]{around};',
            f'way["tourism"~"^(museum|gallery|attraction|viewpoint|artwork|zoo|theme_park|aquarium)$"]{around};',
            f'node["historic"~"^({historic_re})$"]{around};',
            f'way["historic"~"^({historic_re})$"]{around};',
            f'node["leisure"~"^(park|garden|nature_reserve)$"]{around};',
            f'way["leisure"~"^(park|garden|nature_reserve)$"]{around};',
            f'node["natural"~"^(peak|beach)$"]{around};',
            f'node["amenity"~"^(place_of_worship|theatre|cinema|arts_centre|planetarium)$"]{around};',
            f'way["amenity"~"^(place_of_worship|theatre|arts_centre)$"]{around};',
        ]
        body = '\n  '.join(parts)
        return f'[out:json][timeout:25];\n(\n  {body}\n);\nout center tags 500;'

    async def _execute_query(self, query: str) -> List[Dict[str, Any]]:
        client = await self._get_client()
        response = await client.post(self.endpoint, data={'data': query})
        response.raise_for_status()
        data = response.json()
        return data.get('elements', [])

    def _parse_element(self, el: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tags = el.get('tags') or {}
        name = tags.get('name:ru') or tags.get('name') or tags.get('name:en')
        if not name:
            return None

        # Quality gate: drop anything that is structurally a non-tourist
        # facility, even if it carries an incidental historic=* or
        # tourism=* tag (common in OSM for old buildings repurposed as
        # hospitals/schools/shops).
        if not self._passes_quality_gate(tags):
            return None

        if el.get('type') == 'node':
            lat = el.get('lat')
            lon = el.get('lon')
        else:
            center = el.get('center') or {}
            lat = center.get('lat')
            lon = center.get('lon')

        if lat is None or lon is None:
            return None

        category, priority = self._classify(tags)
        # Synthetic rating so OSM POIs can be sensibly ranked against
        # 2GIS/Google entries that DO have ratings. Not a real review
        # score — clearly bounded by priority bucket.
        synth = self._PRIORITY_TO_SYNTH_RATING.get(priority, 2.5)
        return {
            'name': str(name).strip(),
            'lat': float(lat),
            'lon': float(lon),
            'category': category,
            'rating': synth,
            'rating_synthetic': True,
            'address': self._format_address(tags),
            'rubrics': self._tag_list(tags),
            'opening_hours': tags.get('opening_hours'),
            '_priority': priority,
        }

    def _passes_quality_gate(self, tags: Dict[str, str]) -> bool:
        """True iff element looks like a real tourist POI.

        Rejection rules (any one => drop):
        - amenity is in EXCLUDE_TAG_VALUES['amenity'] (hospital, school,
          shop, parking, fuel, etc.)
        - any of EXCLUDE_TAG_KEYS is set (shop, office, craft, ...)
        - element has historic=* but value is not in HISTORIC_WHITELIST
          (Overpass query already pre-filters, but defence-in-depth)

        Acceptance: requires at least one positive tag among tourism,
        whitelisted historic, leisure (park/garden/nature_reserve),
        natural (peak/beach), or amenity in the curated tourism subset.
        """
        amenity = (tags.get('amenity') or '').lower()
        if amenity in self.EXCLUDE_TAG_VALUES.get('amenity', set()):
            return False
        for k in self.EXCLUDE_TAG_KEYS:
            if tags.get(k):
                return False

        historic = (tags.get('historic') or '').lower()
        if historic and historic not in self.HISTORIC_WHITELIST:
            return False

        # Positive signal required.
        if tags.get('tourism') in {
                'museum', 'gallery', 'attraction', 'viewpoint', 'artwork',
                'zoo', 'theme_park', 'aquarium'}:
            return True
        if historic in self.HISTORIC_WHITELIST:
            return True
        if tags.get('leisure') in {'park', 'garden', 'nature_reserve'}:
            return True
        if tags.get('natural') in {'peak', 'beach'}:
            return True
        if amenity in {
                'place_of_worship', 'theatre', 'cinema', 'arts_centre',
                'planetarium'}:
            return True
        return False

    def _classify(self, tags: Dict[str, str]) -> Tuple[str, int]:
        """Return (category, priority). Higher priority = more likely tourist-relevant."""
        if tags.get('tourism') in {'museum', 'gallery'}:
            return 'museum', 10
        if tags.get('tourism') == 'attraction':
            return 'landmark', 9
        if tags.get('tourism') == 'viewpoint':
            return 'viewpoint', 8
        if tags.get('tourism') in {'zoo', 'theme_park', 'aquarium'}:
            return 'entertainment', 8
        if tags.get('historic') in {'castle', 'fort', 'monument', 'memorial', 'ruins', 'archaeological_site'}:
            return 'landmark', 9
        if tags.get('historic') == 'church' or tags.get('amenity') == 'place_of_worship':
            return 'religious', 7
        if tags.get('historic'):
            return 'landmark', 6
        if tags.get('leisure') in {'park', 'garden'}:
            return 'park', 6
        if tags.get('leisure') == 'nature_reserve' or tags.get('natural') == 'peak':
            return 'nature', 6
        if tags.get('natural') == 'beach':
            return 'beach', 6
        if tags.get('amenity') in {'theatre', 'cinema', 'arts_centre', 'planetarium'}:
            return 'entertainment', 7
        return 'landmark', 3

    @staticmethod
    def _format_address(tags: Dict[str, str]) -> str:
        parts = []
        for key in ('addr:street', 'addr:housenumber', 'addr:city'):
            v = tags.get(key)
            if v:
                parts.append(v)
        return ', '.join(parts)

    @staticmethod
    def _tag_list(tags: Dict[str, str]) -> List[str]:
        keys = ('tourism', 'historic', 'leisure', 'natural', 'amenity')
        return [tags[k] for k in keys if k in tags]

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6_371_000
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return R * 2 * atan2(sqrt(a), sqrt(1 - a))

    def _deduplicate(
        self, places: List[Dict[str, Any]], threshold_m: float = 50.0,
    ) -> List[Dict[str, Any]]:
        unique: List[Dict[str, Any]] = []
        for p in places:
            is_dup = False
            for i, existing in enumerate(unique):
                if self._haversine_m(p['lat'], p['lon'], existing['lat'], existing['lon']) < threshold_m:
                    if p.get('_priority', 0) > existing.get('_priority', 0):
                        unique[i] = p
                    is_dup = True
                    break
            if not is_dup:
                unique.append(p)
        return unique

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
