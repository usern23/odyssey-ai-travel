from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import httpx
from src.common.configs.settings import settings
logger = logging.getLogger(__name__)


@dataclass
class FlightOffer:
    price: float
    currency: str
    departure_airport: str
    arrival_airport: str
    departure_time: datetime
    arrival_time: datetime
    airline: str
    duration: str
    stops: int
    booking_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'price': self.price,
            'currency': self.currency,
            'departure_airport': self.departure_airport,
            'arrival_airport': self.arrival_airport,
            'departure_time': self.departure_time.isoformat(),
            'arrival_time': self.arrival_time.isoformat(),
            'airline': self.airline,
            'duration': self.duration,
            'stops': self.stops}


class AmadeusClient:

    def __init__(
            self,
            api_key: Optional[str] = None,
            api_secret: Optional[str] = None,
            base_url: Optional[str] = None):
        self.api_key = api_key or settings.amadeus_api_key
        self.api_secret = api_secret or settings.amadeus_api_secret
        self.base_url = base_url or settings.amadeus_base_url
        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    async def _get_access_token(self) -> str:
        if self._access_token and self._token_expires:
            if datetime.utcnow() < self._token_expires:
                return self._access_token
        if not self.api_key or not self.api_secret:
            raise RuntimeError('Amadeus API credentials not configured')
        async with httpx.AsyncClient() as client:
            response = await client.post(f'{self.base_url}/v1/security/oauth2/token', data={'grant_type': 'client_credentials', 'client_id': self.api_key, 'client_secret': self.api_secret}, headers={'Content-Type': 'application/x-www-form-urlencoded'})
            response.raise_for_status()
            data = response.json()
            self._access_token = data['access_token']
            expires_in = data.get('expires_in', 1800) - 60
            self._token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
            logger.debug('Obtained new Amadeus access token')
            return self._access_token

    async def _make_request(self,
                            method: str,
                            endpoint: str,
                            params: Optional[Dict] = None,
                            json_data: Optional[Dict] = None) -> Dict[str,
                                                                      Any]:
        token = await self._get_access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json'}
        url = f'{self.base_url}{endpoint}'
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == 'GET':
                response = await client.get(url, params=params, headers=headers)
            else:
                response = await client.post(url, json=json_data, headers=headers)
            response.raise_for_status()
            return response.json()

    async def search_flights(
            self,
            origin: str,
            destination: str,
            departure_date: str,
            return_date: Optional[str] = None,
            adults: int = 1,
            max_results: int = 5,
            currency: str = 'RUB') -> List[FlightOffer]:
        params = {
            'originLocationCode': origin.upper(),
            'destinationLocationCode': destination.upper(),
            'departureDate': departure_date,
            'adults': adults,
            'max': max_results,
            'currencyCode': currency}
        if return_date:
            params['returnDate'] = return_date
        try:
            data = await self._make_request('GET', '/v2/shopping/flight-offers', params=params)
        except httpx.HTTPStatusError as e:
            logger.error(f'Amadeus API error: {e.response.text}')
            raise
        offers = []
        for offer in data.get('data', []):
            try:
                price = float(offer['price']['total'])
                currency = offer['price']['currency']
                itinerary = offer['itineraries'][0]
                segments = itinerary['segments']
                first_segment = segments[0]
                last_segment = segments[-1]
                offers.append(
                    FlightOffer(
                        price=price,
                        currency=currency,
                        departure_airport=first_segment['departure']['iataCode'],
                        arrival_airport=last_segment['arrival']['iataCode'],
                        departure_time=datetime.fromisoformat(
                            first_segment['departure']['at'].replace(
                                'Z',
                                '+00:00')),
                        arrival_time=datetime.fromisoformat(
                            last_segment['arrival']['at'].replace(
                                'Z',
                                '+00:00')),
                        airline=first_segment['carrierCode'],
                        duration=itinerary['duration'],
                        stops=len(segments) - 1))
            except (KeyError, ValueError) as e:
                logger.warning(f'Failed to parse flight offer: {e}')
                continue
        return offers

    async def search_airport(
            self, keyword: str, limit: int = 5) -> List[Dict[str, str]]:
        params = {
            'subType': 'AIRPORT,CITY',
            'keyword': keyword,
            'page[limit]': limit}
        try:
            data = await self._make_request('GET', '/v1/reference-data/locations', params=params)
        except httpx.HTTPStatusError as e:
            logger.error(f'Amadeus airport search error: {e.response.text}')
            return []
        results = []
        for location in data.get('data', []):
            results.append(
                {
                    'iata_code': location.get(
                        'iataCode', ''), 'name': location.get(
                        'name', ''), 'city_name': location.get(
                        'address', {}).get(
                        'cityName', ''), 'country_name': location.get(
                            'address', {}).get(
                                'countryName', '')})
        return results

    async def get_flight_inspiration(self,
                                     origin: str,
                                     max_price: Optional[int] = None,
                                     departure_date: Optional[str] = None) -> List[Dict[str,
                                                                                        Any]]:
        params = {'origin': origin.upper()}
        if max_price:
            params['maxPrice'] = max_price
        if departure_date:
            params['departureDate'] = departure_date
        try:
            data = await self._make_request('GET', '/v1/shopping/flight-destinations', params=params)
        except httpx.HTTPStatusError as e:
            logger.error(
                f'Amadeus inspiration search error: {e.response.text}')
            return []
        results = []
        for dest in data.get('data', []):
            results.append(
                {
                    'destination': dest.get(
                        'destination', ''), 'departure_date': dest.get(
                        'departureDate', ''), 'return_date': dest.get(
                        'returnDate', ''), 'price': float(
                        dest.get(
                            'price', {}).get(
                                'total', 0))})
        return results


_client: Optional[AmadeusClient] = None


def get_amadeus_client() -> AmadeusClient:
    global _client
    if _client is None:
        _client = AmadeusClient()
    return _client
