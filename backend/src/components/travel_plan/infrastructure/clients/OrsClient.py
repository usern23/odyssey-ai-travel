from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx
from src.common.configs.settings import settings
logger = logging.getLogger(__name__)


class ORSError(Exception):
    pass


class ORSClient:
    BASE_URL = 'https://api.openrouteservice.org'
    PROFILE_FOOT = 'foot-walking'
    PROFILE_CAR = 'driving-car'
    PROFILE_BIKE = 'cycling-regular'
    PROFILE_TRANSIT = 'public-transport'

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.ors_api_key
        if not self.api_key:
            logger.warning(
                'ORS API key not configured. Set ORS_API_KEY in environment.')
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    'Authorization': self.api_key,
                    'Content-Type': 'application/json'},
                timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client and (not self._client.is_closed):
            await self._client.aclose()

    async def geocode(self,
                      address: str,
                      country: Optional[str] = None) -> Optional[Tuple[float,
                                                                       float]]:
        client = await self._get_client()
        params = {'api_key': self.api_key, 'text': address, 'size': 1}
        if country:
            params['boundary.country'] = country
        try:
            response = await client.get('/geocode/search', params=params)
            response.raise_for_status()
            data = response.json()
            features = data.get('features', [])
            if not features:
                logger.warning(f'No geocoding results for: {address}')
                return None
            coords = features[0]['geometry']['coordinates']
            lat, lon = (coords[1], coords[0])
            logger.debug(f"Geocoded '{address}' → ({lat}, {lon})")
            return (lat, lon)
        except httpx.HTTPStatusError as e:
            logger.error(f'Geocoding error: {e.response.text}')
            raise ORSError(f'Geocoding failed: {e.response.status_code}')
        except Exception as e:
            logger.error(f'Geocoding error: {e}')
            raise ORSError(f'Geocoding failed: {e}')

    async def search_places(
        self,
        query: str,
        focus_lat: Optional[float] = None,
        focus_lon: Optional[float] = None,
        limit: int = 10,
        radius_km: Optional[float] = 50.0,
    ) -> List[Dict[str, Any]]:
        """Free-text search returning multiple ranked results.

        Uses ORS Pelias ``/geocode/search`` endpoint.

        - ``focus.point.*``  — *ranks* nearby results higher.
        - ``boundary.circle.*`` — *filters* hard to a circle around the
          focus point (radius in km, max 1000). This prevents famous
          global landmarks (e.g. London's Royal Albert Hall) from
          drowning out local matches in Manchester etc.

        Each result is a dict with keys: ``name``, ``lat``, ``lon``,
        ``address``, ``layer`` (e.g. venue/address/locality), ``country``.
        """
        client = await self._get_client()
        params: Dict[str, Any] = {
            'api_key': self.api_key,
            'text': query,
            'size': max(1, min(int(limit), 20)),
        }
        if focus_lat is not None and focus_lon is not None:
            params['focus.point.lat'] = focus_lat
            params['focus.point.lon'] = focus_lon
            if radius_km and radius_km > 0:
                params['boundary.circle.lat'] = focus_lat
                params['boundary.circle.lon'] = focus_lon
                params['boundary.circle.radius'] = float(radius_km)
        try:
            response = await client.get('/geocode/search', params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f'Place search error: {e.response.text}')
            raise ORSError(f'Place search failed: {e.response.status_code}')
        except Exception as e:
            logger.error(f'Place search error: {e}')
            raise ORSError(f'Place search failed: {e}')

        results: List[Dict[str, Any]] = []
        for feat in data.get('features', []):
            geom = feat.get('geometry') or {}
            coords = geom.get('coordinates') or []
            if len(coords) < 2:
                continue
            props = feat.get('properties') or {}
            results.append({
                'name': props.get('name') or props.get('label') or query,
                'lat': coords[1],
                'lon': coords[0],
                'address': props.get('label'),
                'layer': props.get('layer'),
                'country': props.get('country'),
                'region': props.get('region'),
                'locality': props.get('locality'),
            })
        return results

    async def get_matrix(self,
                         points: List[Tuple[float,
                                            float]],
                         profile: str = PROFILE_FOOT,
                         metrics: List[str] = None) -> Dict[str,
                                                            Any]:
        if len(points) > 50:
            raise ORSError('Matrix API supports max 50 points in free tier')
        if len(points) < 2:
            raise ORSError('Matrix requires at least 2 points')
        client = await self._get_client()
        locations = [[lon, lat] for lat, lon in points]
        body = {
            'locations': locations,
            'metrics': metrics or [
                'duration',
                'distance'],
            'units': 'm'}
        try:
            response = await client.post(f'/v2/matrix/{profile}', json=body)
            response.raise_for_status()
            data = response.json()
            logger.debug(f'Matrix calculated for {len(points)} points')
            return {
                'durations': data.get(
                    'durations', []), 'distances': data.get(
                    'distances', [])}
        except httpx.HTTPStatusError as e:
            logger.error(f'Matrix error: {e.response.text}')
            raise ORSError(
                f'Matrix calculation failed: {e.response.status_code}')
        except Exception as e:
            logger.error(f'Matrix error: {e}')
            raise ORSError(f'Matrix calculation failed: {e}')

    async def get_directions(self,
                             points: List[Tuple[float,
                                                float]],
                             profile: str = PROFILE_FOOT,
                             geometry: bool = True,
                             instructions: bool = False) -> Dict[str,
                                                                 Any]:
        if len(points) > 50:
            raise ORSError('Directions API supports max 50 waypoints')
        if len(points) < 2:
            raise ORSError('Directions requires at least 2 points')
        client = await self._get_client()
        coordinates = [[lon, lat] for lat, lon in points]
        body = {
            'coordinates': coordinates,
            'geometry': geometry,
            'instructions': instructions,
            'units': 'm'}
        if geometry:
            body['geometry_simplify'] = False
        try:
            response = await client.post(f'/v2/directions/{profile}/geojson', json=body)
            response.raise_for_status()
            data = response.json()
            features = data.get('features', [])
            if not features:
                raise ORSError('No route found')
            feature = features[0]
            properties = feature.get('properties', {})
            geometry_data = feature.get('geometry', {})
            segments = properties.get('segments', [])
            result = {
                'distance': properties.get(
                    'summary',
                    {}).get(
                    'distance',
                    0),
                'duration': properties.get(
                    'summary',
                    {}).get(
                    'duration',
                    0),
                'geometry': geometry_data,
                'segments': segments}
            logger.debug(
                f"Route calculated: {len(points)} points, {result['distance'] / 1000:.1f} km, {result['duration'] / 60:.0f} min")
            return result
        except httpx.HTTPStatusError as e:
            logger.error(f'Directions error: {e.response.text}')
            raise ORSError(f'Directions failed: {e.response.status_code}')
        except Exception as e:
            logger.error(f'Directions error: {e}')
            raise ORSError(f'Directions failed: {e}')

    async def get_directions_summary_only(
            self, points: List[Tuple[float, float]], profile: str = PROFILE_FOOT) -> Dict[str, float]:
        result = await self.get_directions(points, profile=profile, geometry=False, instructions=False)
        return {
            'distance_km': result['distance'] / 1000,
            'duration_min': result['duration'] / 60}

    async def calculate_route_with_waypoints(self,
                                             hotel: Tuple[float,
                                                          float],
                                             daily_waypoints: List[List[Tuple[float,
                                                                              float]]],
                                             profile: str = PROFILE_FOOT) -> Dict[str,
                                                                                  Any]:
        all_points = []
        day_boundaries = []
        for day_idx, day_points in enumerate(daily_waypoints):
            day_boundaries.append(len(all_points))
            all_points.append(hotel)
            all_points.extend(day_points)
        all_points.append(hotel)
        if len(all_points) > 50:
            logger.warning(
                f'Route has {len(all_points)} points, may need to split')
        route = await self.get_directions(all_points, profile=profile)
        segments = route.get('segments', [])
        daily_segments = []
        current_segment_idx = 0
        for day_idx, day_points in enumerate(daily_waypoints):
            num_legs = len(day_points) + 1
            day_distance = 0
            day_duration = 0
            leg_durations = []
            for _ in range(num_legs):
                if current_segment_idx < len(segments):
                    seg = segments[current_segment_idx]
                    day_distance += seg.get('distance', 0)
                    day_duration += seg.get('duration', 0)
                    leg_durations.append(seg.get('duration', 0) / 60)
                    current_segment_idx += 1
            daily_segments.append({'day': day_idx + 1,
                                   'distance_km': day_distance / 1000,
                                   'duration_min': day_duration / 60,
                                   'leg_durations_min': leg_durations})
        return {
            'total_distance_km': route['distance'] / 1000,
            'total_duration_min': route['duration'] / 60,
            'geometry': route.get('geometry'),
            'daily_segments': daily_segments}
