from __future__ import annotations
import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Dict, Iterable, Optional
import httpx
from src.common.configs import settings
logger = logging.getLogger(__name__)


class AviasalesTool:
    LATEST_URL = 'https://api.travelpayouts.com/v2/prices/latest'
    CHEAP_URL = 'https://api.travelpayouts.com/v1/prices/cheap'
    AUTOCOMPLETE_URL = 'https://autocomplete.travelpayouts.com/places2'

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or settings.travelpayouts_token

    async def _resolve_iata(self, city_name: str) -> str:
        if not city_name or (len(city_name) == 3 and city_name.isupper()):
            return city_name
        for locale in ['ru', 'en']:
            params = {'term': city_name, 'locale': locale, 'types[]': 'city'}
            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    response = await client.get(self.AUTOCOMPLETE_URL, params=params)
                    response.raise_for_status()
                    data = response.json()
                    if data and isinstance(data, list):
                        code = data[0].get('code')
                        if code:
                            return code
                except (httpx.HTTPError, IndexError, KeyError, ValueError) as exc:
                    logger.warning(
                        "Autocomplete failed for '%s' (locale=%s): %s", city_name, locale, exc)
        logger.warning("Could not resolve IATA for '%s'", city_name)
        return city_name

    async def get_cheapest_flight(self,
                                  origin: str,
                                  destination: str,
                                  start_date: Optional[str] = None,
                                  end_date: Optional[str] = None,
                                  currency: str = 'RUB') -> Dict[str,
                                                                 Any]:
        depart_iso, return_iso = self._normalize_dates(start_date, end_date)
        origin_iata = await self._resolve_iata(origin)
        destination_iata = await self._resolve_iata(destination)
        logger.info(
            'Querying flights: %s->%s (%s — %s)',
            origin_iata, destination_iata, depart_iso, return_iso)
        if not self.api_token:
            logger.error('No API token provided.')
            return {
                'origin': origin_iata,
                'destination': destination_iata,
                'error': 'API token missing',
                'provider': 'travelpayouts'}

        # Query both endpoints in parallel
        latest_task = self._query_latest(origin_iata, destination_iata, depart_iso, currency)
        cheap_task = self._query_cheap(origin_iata, destination_iata, depart_iso, return_iso, currency)
        latest_result, cheap_result = await asyncio.gather(latest_task, cheap_task, return_exceptions=True)

        candidates = []

        # Process /v2/prices/latest
        if isinstance(latest_result, dict) and latest_result.get('price'):
            latest_result['type'] = 'one_way'
            candidates.append(latest_result)

        # Process /v1/prices/cheap
        if isinstance(cheap_result, dict) and cheap_result.get('price'):
            cheap_result['type'] = 'round_trip'
            candidates.append(cheap_result)

        if not candidates:
            logger.info('No tickets found from either endpoint.')
            return {
                'origin': origin_iata,
                'destination': destination_iata,
                'price': None,
                'currency': currency.lower(),
                'provider': 'travelpayouts',
                'requested_start_date': depart_iso,
                'requested_end_date': return_iso,
                'flights': []}

        # Sort by price
        candidates.sort(key=lambda c: c.get('price', float('inf')))

        # Build response with all found options
        flights = []
        for c in candidates:
            flights.append({
                'price': c['price'],
                'currency': currency.lower(),
                'type': c.get('type', 'unknown'),
                'airline': c.get('airline'),
                'departure_at': c.get('departure_at'),
                'return_at': c.get('return_at'),
                'price_found_at': c.get('price_found_at'),
            })

        best = candidates[0]
        return {
            'origin': origin_iata,
            'destination': destination_iata,
            'price': best['price'],
            'currency': currency.lower(),
            'type': best.get('type', 'unknown'),
            'airline': best.get('airline'),
            'provider': 'travelpayouts',
            'requested_start_date': depart_iso,
            'requested_end_date': return_iso,
            'departure_at': best.get('departure_at'),
            'return_at': best.get('return_at'),
            'price_found_at': best.get('price_found_at'),
            'flights': flights}

    async def _query_latest(self, origin: str, destination: str,
                            depart_iso: str, currency: str) -> Optional[Dict[str, Any]]:
        """Query /v2/prices/latest — cached one-way prices by month."""
        params = {
            'token': self.api_token,
            'origin': origin,
            'currency': currency.lower(),
            'period_type': 'month',
            'limit': 30,
            'page': 1,
            'sorting': 'price',
            'beginning_of_period': depart_iso[:7] + '-01',
        }
        if destination:
            params['destination'] = destination
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.get(self.LATEST_URL, params=params)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                logger.warning('Latest API failed: %s', exc)
                return None
        entries = data.get('data', [])
        ticket = self._pick_best_latest_ticket(entries, depart_iso)
        if not ticket:
            return None
        return {
            'price': ticket.get('value'),
            'departure_at': ticket.get('depart_date'),
            'return_at': ticket.get('return_date'),
            'price_found_at': ticket.get('found_at'),
            'airline': None,
        }

    async def _query_cheap(self, origin: str, destination: str,
                           depart_iso: str, return_iso: str,
                           currency: str) -> Optional[Dict[str, Any]]:
        """Query /v1/prices/cheap — round-trip prices."""
        params = {
            'token': self.api_token,
            'origin': origin,
            'destination': destination,
            'depart_date': depart_iso[:7],
            'return_date': return_iso[:7],
            'currency': currency.lower(),
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.get(self.CHEAP_URL, params=params)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                logger.warning('Cheap API failed: %s', exc)
                return None
        tickets = data.get('data', {})
        ticket = self._pick_closest_ticket(tickets.get(destination, {}), depart_iso)
        if not ticket:
            return None
        return {
            'price': ticket.get('price'),
            'departure_at': ticket.get('departure_at', '')[:10] if ticket.get('departure_at') else None,
            'return_at': ticket.get('return_at', '')[:10] if ticket.get('return_at') else None,
            'price_found_at': ticket.get('found_at'),
            'airline': ticket.get('airline'),
        }

    @staticmethod
    def _pick_best_latest_ticket(
            entries: list, target_date: str) -> Optional[Dict[str, Any]]:
        if not entries:
            return None
        target = date.fromisoformat(target_date)
        best = None
        best_delta = timedelta(days=10000)
        for entry in entries:
            depart_str = entry.get('depart_date')
            if not depart_str:
                continue
            try:
                depart_date = date.fromisoformat(depart_str)
            except ValueError:
                continue
            delta = abs(depart_date - target)
            if delta < best_delta:
                best_delta = delta
                best = entry
            elif delta == best_delta:
                if entry.get(
                        'value',
                        float('inf')) < best.get(
                        'value',
                        float('inf')):
                    best = entry
        return best

    @staticmethod
    def _normalize_dates(
            start_date: Optional[str], end_date: Optional[str]) -> tuple[str, str]:
        today = date.today()

        def _parse(value: Optional[str]) -> Optional[date]:
            if not value:
                return None
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        depart = _parse(start_date) or today
        if depart < today:
            depart = today
        returned = _parse(end_date) or depart + timedelta(days=7)
        if returned <= depart:
            returned = depart + timedelta(days=7)
        return (depart.isoformat(), returned.isoformat())

    @staticmethod
    def _pick_closest_ticket(
            entries: Any, target_date: str) -> Optional[Dict[str, Any]]:
        if isinstance(entries, dict):
            candidates: Iterable[Dict[str, Any]] = entries.values()
        elif isinstance(entries, list):
            candidates = entries
        else:
            return None
        target = date.fromisoformat(target_date)
        best = None
        best_delta = timedelta(days=10000)
        min_price = float('inf')
        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            price = entry.get('price')
            if price is None:
                continue
            try:
                numeric_price = float(price)
            except (TypeError, ValueError):
                continue
            depart_str = entry.get('departure_at')
            if not depart_str:
                continue
            try:
                depart_date = date.fromisoformat(depart_str[:10])
            except ValueError:
                continue
            delta = abs(depart_date - target)
            if delta < best_delta or (
                    delta == best_delta and numeric_price < min_price):
                best_delta = delta
                min_price = numeric_price
                best = entry
        return best
