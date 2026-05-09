from __future__ import annotations
import asyncio
import json
import logging
from typing import Any, Optional, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.agent.infrastructure.tools.strategic.TravelPlannerTool import TravelPlannerTool
from src.common.events.rabbitmq import publish_event
from src.common.events.types import TravelPlanGeneratedEvent
logger = logging.getLogger(__name__)


class GenerateTravelPlanInput(BaseModel):
    user_id: int = Field(
        description='ID пользователя (из контекста USER_ID)')
    destination: str = Field(
        description="Город или регион путешествия (например: 'Санкт-Петербург', 'Париж')")
    places_json: str = Field(
        description='JSON массив мест для посещения. Формат:\n[{"name": "Эрмитаж", "lat": 59.9398, "lon": 30.3146, "category": "museum", "visit_duration_min": 180, "rating": 4.8, "price_level": 4}, ...]\nКатегории: museum, landmark, park, restaurant, cafe, religious, entertainment, shopping, hotel, other')
    hotel_name: str = Field(description='Название отеля или адрес проживания')
    hotel_lat: float = Field(description='Широта отеля')
    hotel_lon: float = Field(description='Долгота отеля')
    start_date: str = Field(description='Дата начала в формате YYYY-MM-DD')
    num_days: int = Field(description='Количество дней путешествия')
    hours_per_day: float = Field(
        default=8.0,
        description='Доступные часы в день для экскурсий (по умолчанию 8)')
    target_places_per_day: Optional[int] = Field(
        default=None,
        description='Желаемое количество мест в день (например 10 для активного темпа)')
    end_hour: Optional[int] = Field(
        default=None,
        description='Час окончания активного дня (по умолчанию 22). Берётся из plan_end_hour TRIP CONTEXT, если задан пользователем в ручном билдере.')


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
        description='Город для уточнения поиска. Для отелей и сетевых названий указывать ОБЯЗАТЕЛЬНО.')


class GetTravelPlanDayInput(BaseModel):
    day_number: int = Field(
        description='Номер дня в уже созданном плане путешествия, начиная с 1')


class GenerateTravelPlanTool(BaseTool):
    name: str = 'generate_travel_plan'
    description: str = 'Создаёт оптимизированный план путешествия с маршрутами.\n\nКОГДА ИСПОЛЬЗОВАТЬ:\n- Пользователь просит составить план/маршрут путешествия\n- Нужно организовать посещение нескольких мест по дням\n- Требуется оптимальный порядок посещения достопримечательностей\n\nПЕРЕД ИСПОЛЬЗОВАНИЕМ:\n1. Найдите координаты всех мест через search_places (укажите 20+ мест)\n2. Узнайте адрес отеля и его координаты\n3. Передайте user_id из контекста (USER_ID)\n\nАлгоритм автоматически загрузит профиль пользователя (предпочтения категорий, бюджет, активность)\nи учтёт их при оптимизации маршрута.\n\nРЕЗУЛЬТАТ:\n- Расписание по дням с временем\n- Маршрут, оптимизированный по качеству мест с учётом предпочтений\n- Общая дистанция и время в пути'
    args_schema: Type[BaseModel] = GenerateTravelPlanInput
    travel_planner: TravelPlannerTool = Field(exclude=True)
    chat_id: int = Field(exclude=True)
    db_session: Any = Field(default=None, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    async def _load_user_profile(
        self, user_id: int,
    ) -> tuple[float, float, dict[str, float] | None, int | None, int, int, int, dict[str, bool], Optional[str]]:
        """Load hours, b_max, user_preferences, places_per_day, start_hour, end_hour, meal_count, food_prefs, pace."""
        if not self.db_session:
            return 8.0, float('inf'), None, None, 10, 22, 2, {}, None
        try:
            from sqlalchemy import select
            from src.components.users.infrastructure.models import UserProfile
            result = await self.db_session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id))
            profile = result.scalar_one_or_none()
            if not profile:
                return 8.0, float('inf'), None, None, 10, 22, 2, {}, None
            pace_value: Optional[str] = None
            try:
                level = profile.activity_level
                pace_value = level.value if hasattr(level, 'value') else str(level) if level else None
            except Exception:
                pace_value = None
            return (
                profile.get_hours_per_day(),
                profile.get_budget_limit(),
                profile.get_sa_user_preferences(),
                profile.get_places_per_day(),
                int(profile.start_hour or 10),
                int(profile.get_effective_end_hour()),
                int(profile.meal_count_per_day or 2),
                dict(profile.food_preferences or {}),
                pace_value,
            )
        except Exception as e:
            logger.warning(f'Failed to load user profile for plan: {e}')
            return 8.0, float('inf'), None, None, 10, 22, 2, {}, None

    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(
            self,
            user_id: int,
            destination: str,
            places_json: str,
            hotel_name: str,
            hotel_lat: float,
            hotel_lon: float,
            start_date: str,
            num_days: int,
            hours_per_day: float = 8.0,
            target_places_per_day: Optional[int] = None,
            end_hour: Optional[int] = None) -> str:
        profile_hours, b_max, user_prefs, profile_places, start_hour, profile_end_hour, meal_count, food_prefs, pace = await self._load_user_profile(user_id)
        effective_hours = profile_hours if hours_per_day == 8.0 else hours_per_day
        # Tempo (places/day): trust the user's explicit profile target
        # (calm=5, moderate=8, active=10) when it's available. The
        # service-side ``compute_points_per_day`` formula stays as a
        # fallback only — it tends to undershoot the profile (e.g. 5
        # for moderate at 10:00–22:00) which surprises the user who
        # explicitly asked for a comfortable tempo.
        if target_places_per_day is not None:
            effective_target = target_places_per_day
        elif profile_places:
            effective_target = profile_places
        else:
            effective_target = None  # service falls back to formula
        result = await self.travel_planner.generate_travel_plan(
            chat_id=self.chat_id, destination=destination,
            places_json=places_json, hotel_name=hotel_name,
            hotel_lat=hotel_lat, hotel_lon=hotel_lon,
            start_date=start_date, num_days=num_days,
            hours_per_day=effective_hours, b_max_per_day=b_max,
            user_preferences=user_prefs,
            target_places_per_day=effective_target,
            start_hour=start_hour,
            end_hour=int(end_hour) if end_hour is not None else profile_end_hour,
            meal_count_per_day=meal_count,
            food_preferences=food_prefs,
            pace=pace,
        )
        if result['success']:
            try:
                await publish_event(TravelPlanGeneratedEvent(
                    chat_id=self.chat_id,
                    user_id=user_id,
                    plan_data=json.dumps(result['plan_data'], default=str)))
                logger.info(f'Published TravelPlanGeneratedEvent for chat {self.chat_id}')
            except Exception as e:
                logger.warning(f'Failed to publish TravelPlanGeneratedEvent: {e}')
            return (f"✅ План путешествия создан!\n\n{result['plan_markdown']}\n\n"
                    f"📊 Статистика:\n- Мест: {result['total_places']}\n"
                    f"- Общее расстояние: {result['total_distance_km']} км\n"
                    f"- Время в пути: {result['total_travel_time_min']} мин")
        else:
            error_msg = result.get('message', result.get('error', 'Неизвестная ошибка'))
            return f"❌ Ошибка: {error_msg}"


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
    description: str = 'Показывает текущий план путешествия.\n\nКОГДА ИСПОЛЬЗОВАТЬ:\n- Пользователь спрашивает про уже созданный план\n- Нужно напомнить расписание\n- Пользователь просит объяснить, пересказать или уточнить существующий маршрут\n- Перед внесением изменений\n\nВАЖНО:\n- Используй этот инструмент вместо generate_travel_plan, если план уже существует\n- Не пересоздавай маршрут заново для follow-up вопросов по текущему плану'
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


class GetTravelPlanDayTool(BaseTool):
    name: str = 'get_travel_plan_day'
    description: str = 'Показывает один конкретный день уже созданного плана путешествия.\n\nКОГДА ИСПОЛЬЗОВАТЬ:\n- Пользователь спрашивает про "день 1", "первый день", "день 3" и т.д.\n- Нужно подробно разобрать места только за один день\n- Пользователь просит рассказать о местах именно из существующего дня маршрута\n\nВАЖНО:\n- Используй этот инструмент вместо generate_travel_plan для вопросов по уже созданному маршруту\n- Не меняй порядок мест и не подменяй их новыми, если пользователь не просил пересобрать план'
    args_schema: Type[BaseModel] = GetTravelPlanDayInput
    travel_planner: TravelPlannerTool = Field(exclude=True)
    chat_id: int = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, day_number: int) -> str:
        result = await self.travel_planner.get_plan_day(self.chat_id, day_number)
        if result['success']:
            return result['day_markdown']
        return f"❌ {result['message']}"


class GeocodeTool(BaseTool):
    name: str = 'geocode_address'
    description: str = 'Преобразует адрес в координаты (широта, долгота).\n\nКОГДА ИСПОЛЬЗОВАТЬ:\n- Нужно узнать координаты места\n- Пользователь указал только название/адрес без координат\n- Для добавления места в план нужны точные координаты\n\nВАЖНО ДЛЯ ОТЕЛЕЙ:\n- Если пользователь назвал отель или сетевой бренд, ОБЯЗАТЕЛЬНО передай city\n- Для travel plan ищи отель только через geocode_address, не через web_search\n- Если результат не совпадает с указанным городом, считай геокодирование неуспешным'
    args_schema: Type[BaseModel] = GeocodeInput
    travel_planner: TravelPlannerTool = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, address: str, city: Optional[str] = None) -> str:
        result = await self.travel_planner.geocode_address(address, city)
        if result['success']:
            return (f"📍 Координаты для '{result['address']}':\n"
                    f"Широта: {result['lat']}\nДолгота: {result['lon']}")
        else:
            return f"❌ {result['message']}"


class ShowRouteMapTool(BaseTool):
    name: str = 'show_route_map'
    description: str = 'Генерирует интерактивную карту текущего плана путешествия.\n\nКОГДА ИСПОЛЬЗОВАТЬ:\n- Пользователь просит показать маршрут на карте\n- После создания плана, для визуализации маршрута\n- Пользователь хочет увидеть расположение всех мест\n\nРЕЗУЛЬТАТ:\n- HTML-карта с маркерами всех мест\n- Маршруты по дням разными цветами\n- Отель отмечен красным маркером\n- Можно включать/выключать дни'
    travel_planner: TravelPlannerTool = Field(exclude=True)
    chat_id: int = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self) -> str:
        return asyncio.run(self._arun())

    async def _arun(self) -> str:
        plan = await self.travel_planner._get_plan(self.chat_id)
        if not plan:
            return "❌ Нет активного плана. Сначала создайте план путешествия."
        try:
            from src.components.agent.infrastructure.tools.auxiliary.RouteMapGenerator import generate_route_map, store_map_html
            html = generate_route_map(plan)
            store_map_html(self.chat_id, html)
            return (
                f"🗺️ Карта маршрута сгенерирована!\n\n"
                f"Маршрут включает {plan.total_places} мест за {plan.num_days} дней.\n"
                f"Общее расстояние: {plan.total_distance_km:.1f} км."
            )
        except Exception as e:
            logger.error(f'Error generating route map: {e}', exc_info=True)
            return f"❌ Ошибка при генерации карты: {e}"


class SetTripHotelInput(BaseModel):
    hotel_name: str = Field(
        description='Название отеля или адрес проживания, как пользователь его назвал')
    address: Optional[str] = Field(
        default=None,
        description='Полный адрес отеля, если он отличается от hotel_name (улица, дом, район)')


class SetTripHotelTool(BaseTool):
    """Persist user's chosen accommodation into the chat's trip.

    The agent calls this whenever the user mentions where they plan to
    stay (hotel name or address). The hotel is geocoded once, stored
    inside ``trip.generated_plan`` (preserving the manual-builder
    ``plan_data`` wrapping when present) and becomes visible on the
    next agent turn via ``plan_hotel_*`` context fields — so the agent
    no longer asks about accommodation again.
    """

    name: str = 'set_trip_hotel'
    description: str = (
        'Сохраняет отель/место проживания в текущую поездку.\n\n'
        'КОГДА ИСПОЛЬЗОВАТЬ:\n'
        '- Пользователь назвал отель/адрес проживания в чате '
        '(даже если план ещё не строится)\n'
        '- В TRIP CONTEXT нет plan_hotel_name, либо пользователь хочет '
        'сменить место проживания\n\n'
        'ЧТО ДЕЛАЕТ:\n'
        '- Геокодирует адрес с учётом города поездки\n'
        '- Записывает hotel в trip.generated_plan, чтобы информация '
        'сохранилась между сообщениями\n\n'
        'ПОСЛЕ ВЫЗОВА: больше НЕ спрашивай у пользователя про отель.'
    )
    args_schema: Type[BaseModel] = SetTripHotelInput
    travel_planner: TravelPlannerTool = Field(exclude=True)
    chat_id: int = Field(exclude=True)
    db_session: Any = Field(default=None, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(
            self,
            hotel_name: str,
            address: Optional[str] = None) -> str:
        if not self.db_session:
            return '❌ Внутренняя ошибка: нет сессии БД для записи отеля.'
        try:
            from sqlalchemy import select
            from src.components.chats.infrastructure.models import Chat
            result = await self.db_session.execute(
                select(Chat).where(Chat.id == self.chat_id))
            chat = result.scalar_one_or_none()
            if not chat or not chat.trip_id:
                return ('❌ Чат пока не привязан к поездке. Сначала '
                        'вызовите collect_trip_data, потом сохраните отель.')
            from src.components.trips.infrastructure.models.TripModel import Trip
            trip_result = await self.db_session.execute(
                select(Trip).where(Trip.id == chat.trip_id))
            trip = trip_result.scalar_one_or_none()
            if not trip:
                return '❌ Поездка не найдена.'

            city = (trip.destination or '').strip() or None
            geo_query = (address or hotel_name).strip()
            geo = await self.travel_planner.geocode_address(geo_query, city)
            if not geo.get('success'):
                return (
                    f"❌ Не удалось определить координаты для '{geo_query}'"
                    + (f' в городе {city}' if city else '')
                    + '. Попросите пользователя уточнить адрес.'
                )
            lat = float(geo['lat'])
            lon = float(geo['lon'])
            resolved_address = geo.get('address') or address or hotel_name

            # Preserve the storage shape: manual builder uses a
            # ``{plan_data: {...}, version, source}`` wrapper, plain
            # chat trips store the inner dict directly. We mirror
            # whichever format is already on disk and create a manual
            # wrapper if the plan is empty.
            existing = dict(trip.generated_plan or {})
            wrapped = isinstance(existing.get('plan_data'), dict)
            if wrapped:
                inner = dict(existing['plan_data'])
            elif existing:
                inner = existing
            else:
                inner = {}

            hotel_dict = {
                'name': hotel_name,
                'lat': lat,
                'lon': lon,
                'address': resolved_address,
                'category': 'hotel',
                'visit_duration_min': 0,
                'source': 'chat',
            }
            inner['hotel'] = hotel_dict
            if not inner.get('destination') and city:
                inner['destination'] = city

            if wrapped or not existing:
                outer = dict(existing) if wrapped else {}
                outer['plan_data'] = inner
                outer.setdefault('source', 'manual')
                try:
                    outer['version'] = int(outer.get('version') or 0) + 1
                except Exception:
                    outer['version'] = 1
                trip.generated_plan = outer
            else:
                trip.generated_plan = inner

            # SQLAlchemy doesn't auto-detect mutations on JSONB dicts
            # unless the column is mapped as Mutable; mark dirty to be safe.
            try:
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(trip, 'generated_plan')
            except Exception:
                pass
            await self.db_session.commit()

            # Refresh the in-memory plan cache so any subsequent
            # planner tool call sees the new hotel.
            cached = self.travel_planner._current_plans.get(self.chat_id)
            if cached is not None:
                try:
                    from src.components.travel_plan.domain.TravelPlanEntities import Place, PlaceCategory
                    cached.hotel = Place(
                        name=hotel_name,
                        lat=lat,
                        lon=lon,
                        category=PlaceCategory.HOTEL,
                        visit_duration_min=0,
                        address=resolved_address,
                        description=resolved_address,
                        source='chat',
                    )
                except Exception as e:
                    logger.debug(f'Could not update cached plan hotel: {e}')

            return (
                f"✅ Отель сохранён в поездку: {hotel_name}"
                + (f" ({resolved_address})" if resolved_address and resolved_address != hotel_name else '')
                + f". Координаты: lat={lat}, lon={lon}."
                + ' Используй эти координаты в generate_travel_plan и больше не уточняй место проживания у пользователя.'
            )
        except Exception as e:
            logger.error(f'set_trip_hotel failed: {e}', exc_info=True)
            try:
                await self.db_session.rollback()
            except Exception:
                pass
            return f'❌ Не удалось сохранить отель: {e}'


class ReplanDayInput(BaseModel):
    day_number: int = Field(
        description='Номер дня в плане путешествия, который нужно перепланировать (начиная с 1)')
    current_datetime_iso: Optional[str] = Field(
        default=None,
        description='Текущее время в формате ISO-8601 (например 2025-06-15T13:30:00). Если не указано — берётся текущий момент.')
    visited_place_names: Optional[list[str]] = Field(
        default=None,
        description='Названия мест, которые пользователь уже посетил сегодня и которые нужно исключить из нового плана')
    additional_candidates_json: Optional[str] = Field(
        default=None,
        description='Опциональный JSON массив новых мест-кандидатов для добавления в пул (тот же формат, что и в generate_travel_plan)')


class ReplanDayTool(BaseTool):
    name: str = 'replan_day'
    description: str = (
        'Перепланирует один день уже созданного плана путешествия с учётом текущего времени, погоды и часов работы мест.\n\n'
        'КОГДА ИСПОЛЬЗОВАТЬ:\n'
        '- Пользователь сообщил, что план дня сломался (опоздание, дождь, закрыто и т.д.)\n'
        '- Нужно пересчитать оставшуюся часть дня начиная с текущего момента\n'
        '- Нужно учесть погодные условия (дождь/снег/жара) для оставшегося дня\n\n'
        'ОСОБЕННОСТИ:\n'
        '- Места из других дней остаются нетронутыми\n'
        '- Закрытые в текущее время POI автоматически исключаются (по opening_hours)\n'
        '- Открытые категории получают/теряют вес в зависимости от погоды\n'
        '- Можно передать visited_place_names чтобы исключить уже посещённое'
    )
    args_schema: Type[BaseModel] = ReplanDayInput
    travel_planner: TravelPlannerTool = Field(exclude=True)
    chat_id: int = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs) -> str:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(
            self,
            day_number: int,
            current_datetime_iso: Optional[str] = None,
            visited_place_names: Optional[list[str]] = None,
            additional_candidates_json: Optional[str] = None) -> str:
        result = await self.travel_planner.replan_day(
            chat_id=self.chat_id,
            day_number=day_number,
            current_datetime_iso=current_datetime_iso,
            visited_place_names=visited_place_names,
            additional_candidates_json=additional_candidates_json,
        )
        if result.get('success'):
            return f"✅ {result['message']}\n\n{result.get('day_markdown') or result.get('plan_markdown', '')}"
        return f"❌ {result.get('message', 'Не удалось перепланировать день.')}"


def create_travel_plan_tools(
        travel_planner: TravelPlannerTool,
        chat_id: int,
        db_session: Any = None) -> list[BaseTool]:
    return [
        GenerateTravelPlanTool(
            travel_planner=travel_planner, chat_id=chat_id, db_session=db_session), AddPlaceToTravelPlanTool(
            travel_planner=travel_planner, chat_id=chat_id), RemovePlaceFromTravelPlanTool(
                travel_planner=travel_planner, chat_id=chat_id), GetCurrentTravelPlanTool(
                    travel_planner=travel_planner, chat_id=chat_id), GetTravelPlanDayTool(
                        travel_planner=travel_planner, chat_id=chat_id), GeocodeTool(
                        travel_planner=travel_planner), ShowRouteMapTool(
                            travel_planner=travel_planner, chat_id=chat_id),
        SetTripHotelTool(
            travel_planner=travel_planner, chat_id=chat_id, db_session=db_session),
        ReplanDayTool(travel_planner=travel_planner, chat_id=chat_id)]
