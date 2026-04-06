from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from src.components.agent.infrastructure.tools.auxiliary.aviasales import AviasalesTool
from src.components.agent.infrastructure.tools.auxiliary.amadeus import AmadeusClient, get_amadeus_client
from src.components.agent.infrastructure.tools.strategic.destination_suggester import DestinationSuggester
from src.components.agent.infrastructure.tools.strategic.trip_data_collector import TripDataCollector
logger = logging.getLogger(__name__)


class DestinationSuggesterInput(BaseModel):
    user_id: int = Field(description='ID of the user')
    interests: Optional[List[str]] = Field(
        default=None, description="List of interests, e.g. ['музеи', 'пляж', 'горы', 'кухня']")
    budget: Optional[str] = Field(
        default=None,
        description="Budget preference: 'budget', 'mid_range', or 'luxury'")
    season: Optional[str] = Field(
        default=None,
        description="Travel season, e.g. 'лето', 'зима', 'весна', 'осень'")
    region: Optional[str] = Field(
        default=None,
        description="Preferred region, e.g. 'Европа', 'Азия', 'Латинская Америка'")
    limit: int = Field(
        default=5,
        description='Number of destinations to suggest')


class DestinationSuggesterLangTool(BaseTool):
    name: str = 'destination_suggester'
    description: str = "Suggest travel destinations based on user preferences. Returns descriptions of recommended cities/countries. Does NOT search for flights - use suggest_flights for that. Use this when user asks 'where should I go?' or 'recommend a destination'."
    args_schema: Type[BaseModel] = DestinationSuggesterInput
    _tool: DestinationSuggester

    def __init__(self, tool: DestinationSuggester, **kwargs: Any):
        super().__init__(**kwargs)
        self._tool = tool

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError('Use _arun for async tool')

    async def _arun(self,
                    user_id: int,
                    interests: Optional[List[str]] = None,
                    budget: Optional[str] = None,
                    season: Optional[str] = None,
                    region: Optional[str] = None,
                    limit: int = 5) -> Dict[str,
                                            Any]:
        return await self._tool.suggest(user_id=user_id, interests=interests, budget=budget, season=season, region=region, limit=limit)


class SuggestFlightsInput(BaseModel):
    origin: str = Field(
        description="Origin city IATA code or name, e.g. 'MOW', 'Москва', 'LED'")
    destination: str = Field(
        description="Destination city IATA code or name, e.g. 'PAR', 'Paris'")
    start_date: Optional[str] = Field(
        default=None, description='Departure date in YYYY-MM-DD format')
    end_date: Optional[str] = Field(
        default=None,
        description='Return date in YYYY-MM-DD format (for round-trip)')


class SuggestFlightsLangTool(BaseTool):
    name: str = 'suggest_flights'
    description: str = 'Search for cheapest flights between two cities. Use this when user asks about flight prices or wants to book tickets. Requires origin and destination cities. Returns price, airline, and flight details. Uses Aviasales API with Amadeus as fallback.'
    args_schema: Type[BaseModel] = SuggestFlightsInput
    _aviasales_tool: AviasalesTool
    _amadeus_client: Optional[AmadeusClient]

    def __init__(
            self,
            aviasales_tool: AviasalesTool,
            amadeus_client: Optional[AmadeusClient] = None,
            **kwargs: Any):
        super().__init__(**kwargs)
        self._aviasales_tool = aviasales_tool
        self._amadeus_client = amadeus_client

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError('Use _arun for async tool')

    async def _arun(self,
                    origin: str,
                    destination: str,
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> Dict[str,
                                                            Any]:
        logger.info(
            f'[SuggestFlights] Received: origin={origin}, destination={destination}, start_date={start_date}, end_date={end_date}')
        logger.info(
            f'[SuggestFlights] Trying Aviasales: {origin} -> {destination}')
        result = await self._aviasales_tool.get_cheapest_flight(origin=origin, destination=destination, start_date=start_date, end_date=end_date)
        has_result = result.get(
            'price') is not None and result.get('error') is None
        if has_result:
            result['provider'] = 'aviasales'
            logger.info(
                f"[SuggestFlights] Aviasales found: {result.get('price')} {result.get('currency')}")
            return result
        logger.info(
            f'[SuggestFlights] Aviasales no results, trying Amadeus fallback')
        amadeus = self._amadeus_client or get_amadeus_client()
        try:
            origin_iata = await self._aviasales_tool._resolve_iata(origin)
            dest_iata = await self._aviasales_tool._resolve_iata(destination)
            from datetime import date, timedelta
            search_date = start_date or (
                date.today() + timedelta(days=1)).isoformat()
            offers = await amadeus.search_flights(origin=origin_iata, destination=dest_iata, departure_date=search_date, return_date=end_date, max_results=5)
            if offers:
                best = offers[0]
                logger.info(
                    f'[SuggestFlights] Amadeus found: {best.price} {best.currency}')
                return {
                    'origin': origin,
                    'destination': destination,
                    'price': best.price,
                    'currency': best.currency.lower(),
                    'provider': 'amadeus',
                    'requested_start_date': search_date,
                    'requested_end_date': end_date,
                    'departure_at': best.departure_time.isoformat() if best.departure_time else None,
                    'return_at': None,
                    'airline': best.airline,
                    'duration': best.duration,
                    'stops': best.stops}
            else:
                logger.info(
                    '[SuggestFlights] Amadeus also returned no results')
        except Exception as e:
            logger.warning(f'[SuggestFlights] Amadeus fallback failed: {e}')
        result['provider'] = 'aviasales'
        result['fallback_tried'] = 'amadeus'
        result['message'] = 'No flights found from Aviasales or Amadeus'
        return result


class TripDataCollectorInput(BaseModel):
    chat_id: int = Field(description='ID of the current chat session')
    user_id: int = Field(description='ID of the user')
    destination: str = Field(
        description="Destination city/country (e.g., 'Paris', 'Thailand')")
    start_date: str = Field(description='Trip start date in YYYY-MM-DD format')
    end_date: str = Field(description='Trip end date in YYYY-MM-DD format')
    budget: str = Field(
        description="Budget preference: 'budget', 'mid_range', or 'luxury'")
    origin: Optional[str] = Field(
        default=None,
        description='Origin city (where traveling from)')
    travelers_count: int = Field(default=1, description='Number of travelers')
    travel_style: Optional[str] = Field(
        default=None,
        description="Travel style: 'relaxed', 'fast_paced', or 'balanced'")
    interests: Optional[List[str]] = Field(
        default=None, description="List of interests (e.g., ['culture', 'food', 'nature'])")


class TripDataCollectorLangTool(BaseTool):
    name: str = 'collect_trip_data'
    description: str = "Collect and save trip planning data. Call this ONLY when you have gathered ALL required info from the user: destination, start_date (YYYY-MM-DD), end_date (YYYY-MM-DD), and budget. This creates the trip record for planning. If any data is missing, ask the user first - don't call this tool."
    args_schema: Type[BaseModel] = TripDataCollectorInput
    _tool: TripDataCollector

    def __init__(self, tool: TripDataCollector, **kwargs: Any):
        super().__init__(**kwargs)
        self._tool = tool

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError('Use _arun for async tool')

    async def _arun(self,
                    chat_id: int,
                    user_id: int,
                    destination: str,
                    start_date: str,
                    end_date: str,
                    budget: str,
                    origin: Optional[str] = None,
                    travelers_count: int = 1,
                    travel_style: Optional[str] = None,
                    interests: Optional[List[str]] = None) -> Dict[str,
                                                                   Any]:
        return await self._tool.collect_and_validate(chat_id=chat_id, user_id=user_id, destination=destination, start_date=start_date, end_date=end_date, budget=budget, origin=origin, travelers_count=travelers_count, travel_style=travel_style, interests=interests)


class WebSearchInput(BaseModel):
    query: str = Field(
        description='Поисковый запрос. Должен быть конкретным и содержать всю необходимую информацию.')
    city: Optional[str] = Field(
        default=None,
        description="Город для контекста поиска (например: 'Санкт-Петербург')")


class WebSearchLangTool(BaseTool):
    name: str = 'web_search'
    description: str = 'Поиск информации в интернете. Используй для:\n- Поиска достопримечательностей с координатами (широта, долгота)\n- Поиска адресов и координат отелей\n- Актуальной информации о часах работы, ценах\n- Поиска рекомендаций и отзывов о местах\n\nВАЖНО: При поиске мест для travel plan, всегда проси вернуть координаты (lat, lon) в формате JSON!\n\nПример запроса: "Найди 5 лучших музеев Санкт-Петербурга с координатами в формате JSON"\n'
    args_schema: Type[BaseModel] = WebSearchInput
    _tool: Any = None

    def __init__(self, tool: Any, **kwargs: Any):
        super().__init__(**kwargs)
        self._tool = tool

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError('Use _arun for async tool')

    async def _arun(self, query: str, city: Optional[str] = None) -> str:
        full_query = f'{query} {city}' if city else query
        result = await self._tool.search(full_query)
        if result['success']:
            return result['content']
        else:
            return f"Ошибка поиска: {result.get('error', 'Неизвестная ошибка')}"


class SearchPlacesInput(BaseModel):
    city: str = Field(description='Город для поиска мест')
    interests: List[str] = Field(
        default=['достопримечательности'],
        description='Список интересов: музеи, архитектура, парки, рестораны и т.д.')
    num_places: int = Field(
        default=50,
        description='Количество мест для поиска (по умолчанию 50, максимум 120)')


class SearchPlacesLangTool(BaseTool):
    name: str = 'search_places'
    description: str = 'Найти достопримечательности и места с координатами для построения маршрута.\n\nИспользует 2GIS API для точных координат и рейтингов + LLM для описаний.\nМожно запрашивать до 120 мест (для длительных поездок 7-10 дней).\n\nВозвращает список мест в формате JSON с полями:\n- name: название места\n- lat: широта (точные координаты из 2GIS)\n- lon: долгота\n- category: категория (museum, landmark, park, restaurant, religious, etc)\n- visit_duration_min: время посещения в минутах\n- rating: рейтинг из реальных отзывов\n- price_level: уровень цен (1-5)\n- description: краткое описание\n\nИспользуй этот инструмент ПЕРЕД вызовом generate_travel_plan!'
    args_schema: Type[BaseModel] = SearchPlacesInput
    _tool: Any = None

    def __init__(self, tool: Any, **kwargs: Any):
        super().__init__(**kwargs)
        self._tool = tool

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError('Use _arun for async tool')

    async def _arun(
            self,
            city: str,
            interests: List[str] = None,
            num_places: int = 50) -> str:
        import json
        result = await self._tool.search_places(city=city, interests=interests or ['достопримечательности'], num_places=num_places)
        if result['success'] and result.get('places'):
            places = result['places']
            return json.dumps(places, ensure_ascii=False, indent=2)
        else:
            return f"Не удалось найти места. Raw response: {result.get('raw_content', 'N/A')[:500]}"
