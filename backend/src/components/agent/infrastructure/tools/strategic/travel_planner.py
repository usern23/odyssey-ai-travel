from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.components.travel_plan.domain.entities import Place, PlaceCategory, TravelPlan
from src.components.travel_plan.application.travel_plan_service import TravelPlanService
from src.components.travel_plan.infrastructure.ors_client import ORSClient
logger = logging.getLogger(__name__)


@dataclass
class TravelPlannerTool:

    def __init__(self, ors_client: Optional[ORSClient] = None,
                 db_session: Optional[AsyncSession] = None):
        self.ors_client = ors_client or ORSClient()
        self.service = TravelPlanService(self.ors_client)
        self._current_plans: Dict[int, TravelPlan] = {}
        self._db_session = db_session

    async def _persist_plan(self, chat_id: int, plan: TravelPlan) -> None:
        self._current_plans[chat_id] = plan

    async def _get_plan(self, chat_id: int) -> Optional[TravelPlan]:
        if chat_id in self._current_plans:
            return self._current_plans[chat_id]
        if not self._db_session:
            return None
        try:
            from src.components.chats.infrastructure.models import Chat
            result = await self._db_session.execute(
                select(Chat).where(
                    Chat.id == chat_id).options(
                    selectinload(
                        Chat.trip)))
            chat = result.scalar_one_or_none()
            if chat and chat.trip and chat.trip.generated_plan:
                plan = TravelPlan.from_dict(chat.trip.generated_plan)
                self._current_plans[chat_id] = plan
                logger.info(
                    f'Loaded travel plan from DB for chat {chat_id}')
                return plan
        except Exception as e:
            logger.warning(f'Failed to load plan from DB: {e}')
        return None

    async def generate_travel_plan(self,
                                   chat_id: int,
                                   destination: str,
                                   places_json: str,
                                   hotel_name: str,
                                   hotel_lat: float,
                                   hotel_lon: float,
                                   start_date: str,
                                   num_days: int,
                                   hours_per_day: float = 8.0,
                                   b_max_per_day: float = float('inf'),
                                   user_preferences: Optional[Dict[str, float]] = None) -> Dict[str,
                                                                       Any]:
        try:
            places_data = json.loads(places_json)
            places = [self._parse_place(p) for p in places_data]
            hotel = Place(
                name=hotel_name,
                lat=hotel_lat,
                lon=hotel_lon,
                category=PlaceCategory.HOTEL,
                visit_duration_min=0)
            trip_start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            plan = await self.service.generate_plan(destination=destination, places=places, hotel=hotel, start_date=trip_start_date, num_days=num_days, hours_per_day=hours_per_day, b_max_per_day=b_max_per_day, user_preferences=user_preferences)
            await self._persist_plan(chat_id, plan)
            return {
                'success': True,
                'plan_markdown': plan.to_markdown(),
                'plan_data': plan.to_dict(),
                'total_places': plan.total_places,
                'total_distance_km': round(
                    plan.total_distance_km,
                    1),
                'total_travel_time_min': plan.total_travel_time_min,
                'message': f'План создан: {plan.total_places} мест за {num_days} дней, {plan.total_distance_km:.1f} км пешком'}
        except json.JSONDecodeError as e:
            logger.error(f'Invalid places JSON: {e}')
            return {
                'success': False,
                'error': f'Неверный формат JSON мест: {e}',
                'message': 'Не удалось разобрать список мест. Проверьте формат данных.'}
        except Exception as e:
            logger.error(f'Error generating plan: {e}', exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'message': f'Ошибка при создании плана: {e}'}

    async def add_place_to_plan(self,
                                chat_id: int,
                                place_name: str,
                                place_lat: float,
                                place_lon: float,
                                category: str = 'other',
                                visit_duration_min: int = 60,
                                description: Optional[str] = None) -> Dict[str,
                                                                           Any]:
        plan = await self._get_plan(chat_id)
        if not plan:
            return {'success': False, 'error': 'Нет активного плана',
                    'message': 'Сначала нужно создать план путешествия.'}
        try:
            new_place = Place(
                name=place_name,
                lat=place_lat,
                lon=place_lon,
                category=PlaceCategory(category) if category in [
                    c.value for c in PlaceCategory] else PlaceCategory.OTHER,
                visit_duration_min=visit_duration_min,
                description=description)
            updated_plan = await self.service.add_place_to_plan(plan, new_place)
            await self._persist_plan(chat_id, updated_plan)
            return {
                'success': True,
                'plan_markdown': updated_plan.to_markdown(),
                'message': f'Добавлено: {place_name}. Маршрут пересчитан.'}
        except Exception as e:
            logger.error(f'Error adding place: {e}')
            return {
                'success': False,
                'error': str(e),
                'message': f'Не удалось добавить место: {e}'}

    async def remove_place_from_plan(
            self, chat_id: int, place_name: str) -> Dict[str, Any]:
        plan = await self._get_plan(chat_id)
        if not plan:
            return {'success': False, 'error': 'Нет активного плана',
                    'message': 'Сначала нужно создать план путешествия.'}
        try:
            updated_plan = await self.service.remove_place_from_plan(plan, place_name)
            await self._persist_plan(chat_id, updated_plan)
            return {
                'success': True,
                'plan_markdown': updated_plan.to_markdown(),
                'message': f'Удалено: {place_name}. Маршрут пересчитан.'}
        except Exception as e:
            logger.error(f'Error removing place: {e}')
            return {
                'success': False,
                'error': str(e),
                'message': f'Не удалось удалить место: {e}'}

    async def get_current_plan(self, chat_id: int) -> Dict[str, Any]:
        plan = await self._get_plan(chat_id)
        if not plan:
            return {
                'success': False,
                'error': 'Нет активного плана',
                'message': 'План ещё не создан.'}
        return {
            'success': True,
            'plan_markdown': plan.to_markdown(),
            'plan_data': plan.to_dict()}

    async def geocode_address(
            self, address: str, city: Optional[str] = None) -> Dict[str, Any]:
        full_address = f'{address}, {city}' if city else address
        try:
            coords = await self.ors_client.geocode(full_address)
            if coords:
                return {
                    'success': True,
                    'lat': coords[0],
                    'lon': coords[1],
                    'address': full_address}
            else:
                return {
                    'success': False,
                    'error': 'Адрес не найден',
                    'message': f'Не удалось найти координаты для: {full_address}'}
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Ошибка геокодирования: {e}'}

    def _parse_place(self, data: Dict[str, Any]) -> Place:
        category_str = data.get('category', 'other')
        try:
            category = PlaceCategory(category_str)
        except ValueError:
            category = PlaceCategory.OTHER
        return Place(
            name=data['name'],
            lat=data['lat'],
            lon=data['lon'],
            category=category,
            visit_duration_min=data.get(
                'visit_duration_min',
                60),
            description=data.get('description'),
            opening_hours=data.get('opening_hours'),
            rating=data.get('rating'),
            price_level=data.get('price_level'))


PLACE_EXAMPLE = '\n{\n  "name": "Эрмитаж",\n  "lat": 59.9398,\n  "lon": 30.3146,\n  "category": "museum",\n  "visit_duration_min": 180,\n  "description": "Один из крупнейших музеев мира",\n  "opening_hours": "10:30-18:00"\n}\n'
PLACES_LIST_EXAMPLE = '\n[\n  {"name": "Эрмитаж", "lat": 59.9398, "lon": 30.3146, "category": "museum", "visit_duration_min": 180},\n  {"name": "Петропавловская крепость", "lat": 59.9500, "lon": 30.3167, "category": "landmark", "visit_duration_min": 120},\n  {"name": "Спас на Крови", "lat": 59.9400, "lon": 30.3289, "category": "religious", "visit_duration_min": 60},\n  {"name": "Русский музей", "lat": 59.9386, "lon": 30.3322, "category": "museum", "visit_duration_min": 120}\n]\n'
