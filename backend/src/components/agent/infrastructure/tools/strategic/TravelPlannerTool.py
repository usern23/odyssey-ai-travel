from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.components.travel_plan.domain.TravelPlanEntities import Place, PlaceCategory, TravelPlan
from src.components.travel_plan.application.services.TravelPlanService import TravelPlanService
from src.components.travel_plan.infrastructure.clients.OrsClient import ORSClient
logger = logging.getLogger(__name__)

HOTEL_CITY_MAX_DISTANCE_KM = 60.0


@dataclass
class TravelPlannerTool:

    def __init__(self, ors_client: Optional[ORSClient] = None,
                 db_session: Optional[AsyncSession] = None):
        self.ors_client = ors_client or ORSClient()
        self.service = TravelPlanService(self.ors_client)
        self._current_plans: Dict[int, TravelPlan] = {}
        self._db_session = db_session

    async def _persist_plan(self, chat_id: int, plan: TravelPlan) -> None:
        # Bump optimistic-locking version on every persist so concurrent
        # manual edits via REST can detect stale state and 409.
        try:
            plan.version = int(getattr(plan, 'version', 1) or 1) + 1
        except Exception:
            plan.version = 2
        self._current_plans[chat_id] = plan
        # Сбрасываем кэш карты, чтобы при следующем запросе фронтенд получил
        # свежий HTML с обновлёнными маркерами/днями.
        try:
            from src.components.agent.infrastructure.tools.auxiliary.RouteMapGenerator import invalidate_map_cache
            invalidate_map_cache(chat_id)
        except Exception as e:
            logger.debug(f'Map cache invalidation skipped: {e}')

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
                                   user_preferences: Optional[Dict[str, float]] = None,
                                   target_places_per_day: Optional[int] = None,
                                   start_hour: int = 10,
                                   end_hour: int = 22,
                                   meal_count_per_day: int = 2,
                                   food_preferences: Optional[Dict[str, bool]] = None,
                                   pace: Optional[str] = None) -> Dict[str,
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

            # ── Weather-aware planning ────────────────────────────────
            # Fetch forecast for the whole trip span (OpenWeather free tier
            # covers up to 5 days). Aggregate per-category modifiers across
            # days by averaging — this nudges the solver towards indoor
            # categories when the trip overlaps with rainy days, without
            # making the modifiers swing too aggressively for a single
            # bad-weather day.
            category_modifiers: Optional[Dict[str, float]] = None
            weather_summary_lines: List[str] = []
            try:
                from src.components.agent.infrastructure.tools.auxiliary.WeatherImpactTool import (
                    WeatherImpactTool,
                )
                weather_tool = WeatherImpactTool()
                forecast = await weather_tool.get_forecast(
                    lat=hotel_lat, lon=hotel_lon,
                    start=trip_start_date, days=num_days,
                )
                if forecast:
                    agg: Dict[str, List[float]] = {}
                    for cond in forecast:
                        mods = weather_tool.compute_category_modifiers(cond)
                        for cat, val in mods.items():
                            agg.setdefault(cat, []).append(val)
                        # Build a one-line summary per day for the plan note.
                        temp_str = (
                            f', {cond.temp_c:+.0f}°C' if cond.temp_c is not None
                            else ''
                        )
                        weather_summary_lines.append(
                            f'{cond.date.strftime("%d.%m")}: '
                            f'{cond.description or cond.condition}{temp_str}'
                        )
                    if agg:
                        category_modifiers = {
                            cat: sum(vals) / len(vals)
                            for cat, vals in agg.items()
                        }
            except Exception as we:
                logger.warning(
                    f'Weather lookup failed, planning without weather modifiers: {we}'
                )

            plan = await self.service.generate_plan(
                destination=destination, places=places, hotel=hotel,
                start_date=trip_start_date, num_days=num_days,
                hours_per_day=hours_per_day, b_max_per_day=b_max_per_day,
                user_preferences=user_preferences,
                min_places_per_day=target_places_per_day,
                start_hour=start_hour,
                end_hour=end_hour,
                meal_count_per_day=meal_count_per_day,
                food_preferences=food_preferences,
                category_modifiers=category_modifiers,
                pace=pace,
            )
            # Surface the forecast in plan_notes so the user sees what
            # weather influenced the plan.
            if weather_summary_lines:
                plan.plan_notes.append({
                    'type': 'weather_forecast',
                    'severity': 'info',
                    'message': 'Прогноз погоды на поездку:\n' + '\n'.join(
                        f'• {line}' for line in weather_summary_lines
                    ),
                    'data': {'days': weather_summary_lines},
                })
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

    async def get_plan_day(
            self, chat_id: int, day_number: int) -> Dict[str, Any]:
        plan = await self._get_plan(chat_id)
        if not plan:
            return {
                'success': False,
                'error': 'Нет активного плана',
                'message': 'План ещё не создан.',
            }
        day = plan.get_day(day_number)
        if not day:
            return {
                'success': False,
                'error': 'День не найден',
                'message': f'В текущем плане нет дня {day_number}.',
            }

        lines = [f'## День {day.day_number} ({day.date})', '']
        for idx, activity in enumerate(day.activities, 1):
            place = activity.place
            time_str = (
                f"{activity.start_time.strftime('%H:%M')}"
                f"–{activity.end_time.strftime('%H:%M')}"
            )
            rating_tag = f" ⭐ {place.rating:.1f}" if place.rating is not None else ''
            lines.append(
                f'{idx}. **{time_str}** — {place.name}{rating_tag} ({place.category.value})'
            )
            if place.description:
                lines.append(f'   {place.description}')
            if place.address:
                lines.append(f'   📍 {place.address}')
            if place.opening_hours:
                lines.append(f'   🕒 {place.opening_hours}')
            if activity.travel_time_from_prev_min:
                lines.append(f'   🚶 {activity.travel_time_from_prev_min} мин от предыдущей точки')
            lines.append('')

        lines.append(
            f'Итог: {len(day.activities)} мест, {day.total_distance_km:.1f} км, '
            f'{day.total_travel_time_min} мин в пути.'
        )
        return {
            'success': True,
            'day_markdown': '\n'.join(lines),
            'day_data': day.to_dict(),
            'plan_destination': plan.destination,
            'hotel_name': plan.hotel.name,
        }

    def _now_at_hotel(self, plan: TravelPlan) -> datetime:
        """Best-effort "now" in the destination's local timezone.

        Uses ``timezonefinder`` (offline lookup) when installed; otherwise
        falls back to UTC. The returned ``datetime`` is naive (tz-stripped)
        to match the rest of the planning code, but its wall-clock value
        corresponds to local time at the hotel coordinates.
        """
        try:
            from timezonefinder import TimezoneFinder  # type: ignore
            from zoneinfo import ZoneInfo
            tz_name = TimezoneFinder().timezone_at(
                lat=plan.hotel.lat, lng=plan.hotel.lon,
            )
            if tz_name:
                return datetime.now(ZoneInfo(tz_name)).replace(tzinfo=None)
        except Exception as e:  # noqa: BLE001 — fallback path
            logger.debug('TZ lookup failed for hotel, using UTC: %s', e)
        return datetime.now(timezone.utc).replace(tzinfo=None)

    async def replan_day(
            self,
            chat_id: int,
            day_number: int,
            current_datetime_iso: Optional[str] = None,
            visited_place_names: Optional[List[str]] = None,
            additional_candidates_json: Optional[str] = None) -> Dict[str, Any]:
        """Re-optimise a single day of the current plan based on context.

        - ``current_datetime_iso``: ISO-8601 timestamp representing "now". If
          omitted, uses the current UTC time.
        - ``visited_place_names``: places already visited today that must be
          excluded from the replanned day.
        - ``additional_candidates_json``: optional JSON array of extra Place
          dicts to inject into the candidate pool (Variant C — on-the-fly
          candidate discovery).
        """
        plan = await self._get_plan(chat_id)
        if not plan:
            return {'success': False, 'error': 'Нет активного плана',
                    'message': 'Сначала нужно создать план путешествия.'}
        try:
            if current_datetime_iso:
                current_dt = datetime.fromisoformat(current_datetime_iso)
            else:
                # Fall back to *local* time of the destination so that
                # opening-hours filtering and "remaining time of the day"
                # arithmetic in TravelPlanService.replan_day make sense.
                # The plan stores no timezone, so we infer it from the
                # hotel coordinates via timezonefinder when available;
                # otherwise we use UTC (only loses up to ±12h).
                current_dt = self._now_at_hotel(plan)
        except ValueError as e:
            return {'success': False, 'error': str(e),
                    'message': f'Некорректный формат времени: {current_datetime_iso}'}

        extra_candidates: List[Place] = []
        if additional_candidates_json:
            try:
                raw = json.loads(additional_candidates_json)
                for item in raw or []:
                    try:
                        extra_candidates.append(Place(
                            name=item['name'],
                            lat=float(item['lat']),
                            lon=float(item['lon']),
                            category=PlaceCategory(item.get('category', 'other')),
                            visit_duration_min=int(item.get('visit_duration_min', 60)),
                            rating=item.get('rating'),
                            price_level=item.get('price_level'),
                            description=item.get('description'),
                            address=item.get('address'),
                            opening_hours=item.get('opening_hours'),
                        ))
                    except Exception as ie:
                        logger.warning(f'Skipping malformed candidate: {ie}')
            except json.JSONDecodeError as e:
                return {'success': False, 'error': str(e),
                        'message': 'additional_candidates_json не валидный JSON.'}

        # Compute weather-based category modifiers for the target day.
        category_modifiers: Optional[Dict[str, float]] = None
        try:
            from src.components.agent.infrastructure.tools.auxiliary.WeatherImpactTool import (
                WeatherImpactTool,
            )
            weather_tool = WeatherImpactTool()
            target_day = plan.get_day(day_number)
            if target_day is not None:
                forecast = await weather_tool.get_forecast(
                    lat=plan.hotel.lat, lon=plan.hotel.lon,
                    start=target_day.date, days=1,
                )
                condition = next(
                    (c for c in forecast if c.date == target_day.date),
                    forecast[0] if forecast else None,
                )
                if condition is not None:
                    category_modifiers = weather_tool.compute_category_modifiers(condition)
        except Exception as we:
            logger.warning(f'Weather lookup failed, replanning without weather modifiers: {we}')

        try:
            updated_plan = await self.service.replan_day(
                plan=plan,
                day_number=day_number,
                current_datetime=current_dt,
                visited_place_names=visited_place_names,
                additional_candidates=extra_candidates or None,
                category_modifiers=category_modifiers,
            )
            await self._persist_plan(chat_id, updated_plan)
            day = updated_plan.get_day(day_number)
            return {
                'success': True,
                'plan_markdown': updated_plan.to_markdown(),
                'day_markdown': day.to_markdown() if day else '',
                'message': f'День {day_number} перепланирован с учётом текущего времени и погоды.',
            }
        except Exception as e:
            logger.error(f'Error in replan_day: {e}', exc_info=True)
            return {'success': False, 'error': str(e),
                    'message': f'Не удалось перепланировать день: {e}'}

    async def geocode_address(
            self, address: str, city: Optional[str] = None) -> Dict[str, Any]:
        full_address = f'{address}, {city}' if city else address
        try:
            if city:
                coords, resolved_query, provider = await self._resolve_hotel_with_city_guard(
                    address=address, city=city,
                )
            else:
                coords = await self.ors_client.geocode(full_address)
                resolved_query = full_address
                provider = 'ors'

            if coords:
                return {
                    'success': True,
                    'lat': coords[0],
                    'lon': coords[1],
                    'address': resolved_query,
                    'provider': provider,
                }
            return {
                'success': False,
                'error': 'Адрес не найден',
                'message': f'Не удалось найти координаты для: {full_address}',
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Ошибка геокодирования: {e}'}

    async def _resolve_hotel_with_city_guard(
            self, address: str, city: str) -> tuple[Optional[tuple[float, float]], str, str]:
        city_center = await self.ors_client.geocode(city)
        queries = self._build_geocode_queries(address, city)
        mismatch_hits: List[tuple[str, float, str]] = []

        # 2GIS is usually the most precise source for hotel POIs in RU/CIS.
        try:
            from src.components.agent.infrastructure.tools.auxiliary.TwoGisClient import TwoGisClient
            twogis = TwoGisClient()
            try:
                for query in queries:
                    coords = await twogis.geocode(query)
                    if not coords:
                        continue
                    if self._is_within_city_scope(coords, city_center):
                        return coords, query, '2gis'
                    if city_center:
                        mismatch_hits.append(
                            (query, self._haversine_km(
                                coords[0], coords[1], city_center[0], city_center[1]), '2gis'))
            finally:
                await twogis.close()
        except Exception as e:
            logger.debug('2GIS hotel geocode skipped for "%s, %s": %s', address, city, e)

        for query in queries:
            coords = await self.ors_client.geocode(query)
            if not coords:
                continue
            if self._is_within_city_scope(coords, city_center):
                return coords, query, 'ors'
            if city_center:
                mismatch_hits.append(
                    (query, self._haversine_km(
                        coords[0], coords[1], city_center[0], city_center[1]), 'ors'))

        if mismatch_hits:
            closest = min(mismatch_hits, key=lambda item: item[1])
            logger.warning(
                'Hotel geocode mismatch for "%s" in "%s": nearest result %.1f km away via %s (%s)',
                address, city, closest[1], closest[2], closest[0],
            )
            raise ValueError(
                f'Найден похожий объект слишком далеко от города {city}. '
                f'Уточните адрес или район отеля.'
            )

        return None, f'{address}, {city}', 'ors'

    @staticmethod
    def _build_geocode_queries(address: str, city: str) -> List[str]:
        variants = [
            f'{address}, {city}',
            f'{city}, {address}',
        ]
        lowered_address = address.lower()
        lowered_city = city.lower()
        if lowered_city in lowered_address:
            return [address]
        unique: List[str] = []
        seen: set[str] = set()
        for query in variants:
            norm = query.strip()
            if norm and norm.lower() not in seen:
                seen.add(norm.lower())
                unique.append(norm)
        return unique

    @staticmethod
    def _is_within_city_scope(
            coords: tuple[float, float],
            city_center: Optional[tuple[float, float]]) -> bool:
        if not city_center:
            return True
        return TravelPlannerTool._haversine_km(
            coords[0], coords[1], city_center[0], city_center[1],
        ) <= HOTEL_CITY_MAX_DISTANCE_KM

    @staticmethod
    def _haversine_km(
            lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_km = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = (
            sin(dlat / 2) ** 2
            + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        )
        return radius_km * 2 * atan2(sqrt(a), sqrt(1 - a))

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
            price_level=data.get('price_level'),
            source=data.get('source'))


PLACE_EXAMPLE = '\n{\n  "name": "Эрмитаж",\n  "lat": 59.9398,\n  "lon": 30.3146,\n  "category": "museum",\n  "visit_duration_min": 180,\n  "description": "Один из крупнейших музеев мира",\n  "opening_hours": "10:30-18:00"\n}\n'
PLACES_LIST_EXAMPLE = '\n[\n  {"name": "Эрмитаж", "lat": 59.9398, "lon": 30.3146, "category": "museum", "visit_duration_min": 180},\n  {"name": "Петропавловская крепость", "lat": 59.9500, "lon": 30.3167, "category": "landmark", "visit_duration_min": 120},\n  {"name": "Спас на Крови", "lat": 59.9400, "lon": 30.3289, "category": "religious", "visit_duration_min": 60},\n  {"name": "Русский музей", "lat": 59.9386, "lon": 30.3322, "category": "museum", "visit_duration_min": 120}\n]\n'
