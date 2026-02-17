from __future__ import annotations
import asyncio
import json
import logging
from typing import Any, Optional, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from src.components.agent.infrastructure.tools.strategic.travel_planner import TravelPlannerTool
logger = logging.getLogger(__name__)


class GenerateTravelPlanInput(BaseModel):
    destination: str = Field(
        description="Город или регион путешествия (например: 'Санкт-Петербург', 'Париж')")
    places_json: str = Field(
        description='JSON массив мест для посещения. Формат:\n[{"name": "Эрмитаж", "lat": 59.9398, "lon": 30.3146, "category": "museum", "visit_duration_min": 180}, ...]\nКатегории: museum, landmark, park, restaurant, cafe, religious, entertainment, shopping, hotel, other')
    hotel_name: str = Field(description='Название отеля или адрес проживания')
    hotel_lat: float = Field(description='Широта отеля')
    hotel_lon: float = Field(description='Долгота отеля')
    start_date: str = Field(description='Дата начала в формате YYYY-MM-DD')
    num_days: int = Field(description='Количество дней путешествия')
    hours_per_day: float = Field(
        default=8.0,
        description='Доступные часы в день для экскурсий (по умолчанию 8)')


class AddPlaceInput(BaseModel):
    place_name: str = Field(description='Название места')
    place_lat: float = Field(description='Широта')
    place_lon: float = Field(description='Долгота')
    category: str = Field(
        default='other',
        description='Категория: museum, landmark, park, restaurant, cafe, religious, entertainment, shopping, other')
    visit_duration_min: int = Field(default=60,
                                    description='Время на посещение в минутах')
    description: Optional[str] = Field(
        default=None, description='Описание места (опционально)')


class RemovePlaceInput(BaseModel):
    place_name: str = Field(description='Название места для удаления')


class GeocodeInput(BaseModel):
    address: str = Field(description='Адрес или название места')
    city: Optional[str] = Field(
        default=None,
        description='Город для уточнения поиска (опционально)')


class GenerateTravelPlanTool(BaseTool):
    name: str = 'generate_travel_plan'
    description: str = 'Создаёт оптимизированный план путешествия с маршрутами.\n\nКОГДА ИСПОЛЬЗОВАТЬ:\n- Пользователь просит составить план/маршрут путешествия\n- Нужно организовать посещение нескольких мест по дням\n- Требуется оптимальный порядок посещения достопримечательностей\n\nПЕРЕД ИСПОЛЬЗОВАНИЕМ:\n1. Найдите координаты всех мест через веб-поиск\n2. Узнайте адрес отеля и его координаты\n3. Уточните даты и количество дней\n\nРЕЗУЛЬТАТ:\n- Расписание по дням с временем\n- Оптимальный маршрут (минимум ходьбы)\n- Общая дистанция и время в пути'
    args_schema: Type[BaseModel] = GenerateTravelPlanInput
    travel_planner: TravelPlannerTool = Field(exclude=True)
    chat_id: int = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(
            self,
            destination: str,
            places_json: str,
            hotel_name: str,
            hotel_lat: float,
            hotel_lon: float,
            start_date: str,
            num_days: int,
            hours_per_day: float = 8.0) -> str:
        result = await self.travel_planner.generate_travel_plan(chat_id=self.chat_id, destination=destination, places_json=places_json, hotel_name=hotel_name, hotel_lat=hotel_lat, hotel_lon=hotel_lon, start_date=start_date, num_days=num_days, hours_per_day=hours_per_day)
        if result['success']:
            return f"✅ План путешествия создан!\n\n{
                result['plan_markdown']}\n\n📊 Статистика:\n- Мест: {
                result['total_places']}\n- Общее расстояние: {
                result['total_distance_km']} км\n- Время в пути: {
                result['total_travel_time_min']} мин"
        else:
            return f"❌ Ошибка: {
                result.get(
                    'message',
                    result.get(
                        'error',
                        'Неизвестная ошибка'))}"


class AddPlaceToTravelPlanTool(BaseTool):
    name: str = 'add_place_to_travel_plan'
    description: str = 'Добавляет новое место в существующий план путешествия.\n\nКОГДА ИСПОЛЬЗОВАТЬ:\n- Пользователь хочет добавить место в план\n- Нужно включить дополнительную достопримечательность\n\nТРЕБУЕТСЯ:\n- Активный план путешествия (создан ранее)\n- Координаты нового места'
    args_schema: Type[BaseModel] = AddPlaceInput
    travel_planner: TravelPlannerTool = Field(exclude=True)
    chat_id: int = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(
            self,
            place_name: str,
            place_lat: float,
            place_lon: float,
            category: str = 'other',
            visit_duration_min: int = 60,
            description: Optional[str] = None) -> str:
        result = await self.travel_planner.add_place_to_plan(chat_id=self.chat_id, place_name=place_name, place_lat=place_lat, place_lon=place_lon, category=category, visit_duration_min=visit_duration_min, description=description)
        if result['success']:
            return f"✅ {result['message']}\n\n{result['plan_markdown']}"
        else:
            return f"❌ {result['message']}"


class RemovePlaceFromTravelPlanTool(BaseTool):
    name: str = 'remove_place_from_travel_plan'
    description: str = 'Удаляет место из существующего плана путешествия.\n\nКОГДА ИСПОЛЬЗОВАТЬ:\n- Пользователь хочет убрать место из плана\n- Место закрыто или недоступно\n- Пользователь передумал посещать'
    args_schema: Type[BaseModel] = RemovePlaceInput
    travel_planner: TravelPlannerTool = Field(exclude=True)
    chat_id: int = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, place_name: str) -> str:
        result = await self.travel_planner.remove_place_from_plan(chat_id=self.chat_id, place_name=place_name)
        if result['success']:
            return f"✅ {result['message']}\n\n{result['plan_markdown']}"
        else:
            return f"❌ {result['message']}"


class GetCurrentTravelPlanTool(BaseTool):
    name: str = 'get_current_travel_plan'
    description: str = 'Показывает текущий план путешествия.\n\nКОГДА ИСПОЛЬЗОВАТЬ:\n- Пользователь спрашивает про текущий план\n- Нужно напомнить расписание\n- Перед внесением изменений'
    travel_planner: TravelPlannerTool = Field(exclude=True)
    chat_id: int = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self) -> str:
        return asyncio.run(self._arun())

    async def _arun(self) -> str:
        result = await self.travel_planner.get_current_plan(self.chat_id)
        if result['success']:
            return result['plan_markdown']
        else:
            return f"❌ {result['message']}"


class GeocodeTool(BaseTool):
    name: str = 'geocode_address'
    description: str = 'Преобразует адрес в координаты (широта, долгота).\n\nКОГДА ИСПОЛЬЗОВАТЬ:\n- Нужно узнать координаты места\n- Пользователь указал только название/адрес без координат\n- Для добавления места в план нужны точные координаты'
    args_schema: Type[BaseModel] = GeocodeInput
    travel_planner: TravelPlannerTool = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, address: str, city: Optional[str] = None) -> str:
        result = await self.travel_planner.geocode_address(address, city)
        if result['success']:
            return f"📍 Координаты для '{
                result['address']}':\nШирота: {
                result['lat']}\nДолгота: {
                result['lon']}"
        else:
            return f"❌ {result['message']}"


def create_travel_plan_tools(
        travel_planner: TravelPlannerTool,
        chat_id: int) -> list[BaseTool]:
    return [
        GenerateTravelPlanTool(
            travel_planner=travel_planner, chat_id=chat_id), AddPlaceToTravelPlanTool(
            travel_planner=travel_planner, chat_id=chat_id), RemovePlaceFromTravelPlanTool(
                travel_planner=travel_planner, chat_id=chat_id), GetCurrentTravelPlanTool(
                    travel_planner=travel_planner, chat_id=chat_id), GeocodeTool(
                        travel_planner=travel_planner)]
