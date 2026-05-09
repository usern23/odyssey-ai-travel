from __future__ import annotations
import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from src.components.travel_plan.domain.TravelPlanEntities import (
    Activity,
    DAY_WINDOW_END,
    DAY_WINDOW_START,
    DayPlan,
    Place,
    PlaceCategory,
    TIME_ROUND_MINUTES,
    TravelPlan,
    resolve_opening_window,
)
from src.components.travel_plan.infrastructure.clients.OrsClient import ORSClient, ORSError
from src.components.travel_plan.application.solvers.TspSolver import TSPSolver, build_distance_matrix_haversine, estimate_walking_time
from src.components.travel_plan.application.solvers.OrienteeringSolver import OrienteeringSolver, OPConfig, OPPlaceParams
logger = logging.getLogger(__name__)

NON_TOURIST_PLACE_KEYWORDS = {
    # Medical
    'медицин', 'медцентр', 'клиник', 'больниц', 'госпиталь',
    'поликлиник', 'диспансер', 'стоматолог', 'роддом', 'перинатальн',
    'травмпункт', 'ветеринар', 'аптек', 'оптика',
    'hospital', 'clinic', 'medical', 'pharmacy', 'dental',
    # Education
    'университет', 'институт', 'колледж', 'школа', 'гимназия', 'лицей',
    'детский сад', 'академия ', 'автошкол', 'языковая школа',
    'university', 'college', 'school', 'kindergarten',
    # Government / public service
    'налогов', 'фнс', 'мфц', 'паспортный', 'военкомат', 'госуслуг',
    'пенсионный фонд', 'росреестр', 'администрация ', 'мэрия ',
    # Banks
    'банк ', 'банкомат', 'отделение банка', 'обмен валют', 'обменник',
    # Offices / industrial
    'бизнес-центр', 'офис', 'склад', 'логистическ', 'промышленн',
    'юридическ', 'нотариус', 'адвокат',
    # Retail noise
    'минимаркет', 'мини-маркет', 'гипермаркет', 'супермаркет',
    'продуктовый', 'гастроном', 'ломбард', 'комиссионн',
    # Auto / fuel
    'автосерви', 'автомойк', 'шиномонт', 'парковк', 'паркинг',
    'заправк', 'азс ', 'parking', 'gas station', 'fuel',
    # Misc service
    'химчистк', 'прачечн', 'ритуальн', 'похоронн', 'кладбищ',
    'крематори', 'типография',
}

# Deterministic mapping pace -> minutes spent per POI
# (visit + average transit + buffer). Used by ``compute_points_per_day``
# so the agent does not have to guess a target on its own.
PACE_MINUTES_PER_POINT: Dict[str, int] = {
    'calm': 150,
    'relaxed': 150,
    'moderate': 110,
    'balanced': 110,
    'active': 80,
    'intense': 80,
    'fast_paced': 80,
}
DEFAULT_PACE = 'moderate'
# Time we mentally subtract from the day window for meals + setup buffer.
PACE_BUFFER_MINUTES_BASE = 30  # generic buffer (commute hotel ↔ first/last)


def compute_points_per_day(
    pace: Optional[str],
    start_time: time,
    end_time: time,
    meal_count: int = 2,
    meal_minutes: int = 60,
) -> int:
    """Deterministic target points-per-day from prefs.

    Formula: ``floor((window − meals − buffer) / minutes_per_point)``.
    Result is clamped to ``[2, 12]`` to keep solver inputs reasonable.
    """
    pace_key = (pace or DEFAULT_PACE).lower()
    minutes_per_point = PACE_MINUTES_PER_POINT.get(
        pace_key, PACE_MINUTES_PER_POINT[DEFAULT_PACE])
    window = max(0, (end_time.hour * 60 + end_time.minute) -
                 (start_time.hour * 60 + start_time.minute))
    effective = window - max(0, meal_count) * meal_minutes - PACE_BUFFER_MINUTES_BASE
    if effective <= 0 or minutes_per_point <= 0:
        return 2
    return max(2, min(12, effective // minutes_per_point))


def _round_up_datetime(dt: datetime, step_minutes: int) -> datetime:
    """Round a datetime forward to the next multiple of ``step_minutes``."""
    if step_minutes <= 1:
        return dt.replace(second=0, microsecond=0)
    total = dt.minute % step_minutes
    base = dt.replace(second=0, microsecond=0)
    if total == 0 and dt.second == 0 and dt.microsecond == 0:
        return base
    delta = step_minutes - (dt.minute % step_minutes)
    if dt.second or dt.microsecond:
        # Always move forward if there were leftover seconds.
        if total == 0:
            delta = step_minutes
    return (base + timedelta(minutes=delta))


class TravelPlanService:
    DEFAULT_START_TIME = DAY_WINDOW_START   # 10:00
    DEFAULT_END_TIME = DAY_WINDOW_END       # 22:00
    DEFAULT_LUNCH_TIME = time(13, 0)
    DEFAULT_DINNER_TIME = time(19, 0)

    def __init__(self, ors_client: Optional[ORSClient] = None):
        self.ors = ors_client or ORSClient()
        self.tsp = TSPSolver()
        self.op = OrienteeringSolver()

    async def generate_plan(
            self,
            destination: str,
            places: List[Place],
            hotel: Place,
            start_date: date,
            num_days: int,
            hours_per_day: float = 8.0,
            b_max_per_day: float = float('inf'),
            start_time: time = DEFAULT_START_TIME,
            use_real_distances: bool = True,
            user_preferences: Optional[Dict[str, float]] = None,
            min_places_per_day: Optional[int] = None,
            start_hour: Optional[int] = None,
            end_hour: Optional[int] = None,
            meal_count_per_day: int = 2,
            food_preferences: Optional[Dict[str, bool]] = None,
            category_modifiers: Optional[Dict[str, float]] = None,
            pace: Optional[str] = None) -> TravelPlan:
        logger.info(
            f'Generating plan for {destination}: {len(places)} places, {num_days} days')
        plan_notes: List[Dict[str, Any]] = []
        if not places:
            return self._empty_plan(destination, hotel, start_date, num_days)

        # Фильтр ресторанов/кафе по food_preferences (веган/халяль/кухни).
        if food_preferences:
            places = self._filter_food_places(places, food_preferences)

        # Убираем «шумные» POI из Overpass/OSM без рейтинга
        # (университеты, площади, отдельные мечети/библиотеки) —
        # они часто всплывают, когда 2GIS недобрал мест.
        places = self._filter_low_signal_places(places, num_days)
        places = self._filter_non_tourist_places(places, num_days)

        # Профильный start_hour (7..12) переопределяет start_time.
        if start_hour is not None:
            try:
                start_time = time(int(start_hour), 0)
            except Exception:
                pass

        # Кап бюджета времени: solver не может работать за пределами
        # активного окна дня [start_time .. effective_end_time]. Если
        # профиль просит 14 ч, а реально влезает 10 ч — берём минимум.
        # ``end_hour`` берётся из плана/поездки (ручной билдер, профиль),
        # иначе — стандартный конец дня (22:00).
        try:
            end_h_int = int(end_hour) if end_hour is not None else DAY_WINDOW_END.hour
        except Exception:
            end_h_int = DAY_WINDOW_END.hour
        end_h_int = max(start_time.hour + 1, min(24, end_h_int))
        effective_end_time = (
            time(end_h_int, 0) if end_h_int < 24 else time(23, 59)
        )
        max_window_hours = max(
            1.0, float(end_h_int - start_time.hour),
        )
        effective_hours_per_day = min(hours_per_day, max_window_hours)
        if effective_hours_per_day != hours_per_day:
            logger.info(
                'hours_per_day capped: %.1f → %.1f (window %s–%s)',
                hours_per_day, effective_hours_per_day,
                start_time.strftime('%H:%M'),
                effective_end_time.strftime('%H:%M'),
            )
            plan_notes.append({
                'type': 'pace_window_capped',
                'severity': 'info',
                'message': (
                    f'Дневное окно сокращено с {hours_per_day:.0f} до '
                    f'{effective_hours_per_day:.0f} часов (ограничение активного окна '
                    f'{start_time.strftime("%H:%M")}–{effective_end_time.strftime("%H:%M")}).'
                ),
                'data': {
                    'requested': hours_per_day,
                    'effective': effective_hours_per_day,
                },
            })

        # Deterministic target if caller didn't provide one. We compute it
        # from pace (calm/moderate/active) + dayly window + meals so the
        # answer is reproducible and explainable to the user.
        if not min_places_per_day or int(min_places_per_day) <= 0:
            min_places_per_day = compute_points_per_day(
                pace=pace,
                start_time=start_time,
                end_time=effective_end_time,
                meal_count=meal_count_per_day,
            )
            logger.info(
                'points_per_day computed deterministically: %d (pace=%s, '
                'window=%s–%s, meals=%d)',
                min_places_per_day, pace or DEFAULT_PACE,
                start_time.strftime('%H:%M'),
                effective_end_time.strftime('%H:%M'),
                meal_count_per_day,
            )

        # Строим матрицу расстояний для всех кандидатов + отель (depot)
        all_points = [(hotel.lat, hotel.lon)] + [(p.lat, p.lon) for p in places]
        if use_real_distances:
            try:
                distance_matrix = await self._get_ors_matrix(all_points)
            except ORSError as e:
                logger.warning(f'ORS Matrix failed, using haversine: {e}')
                distance_matrix = build_distance_matrix_haversine(all_points)
        else:
            distance_matrix = build_distance_matrix_haversine(all_points)

        # Решаем задачу командного ориентирования (TOP)
        optimized_days = self._solve_orienteering(
            places=places,
            distance_matrix=distance_matrix,
            num_days=num_days,
            hours_per_day=effective_hours_per_day,
            b_max_per_day=b_max_per_day,
            user_preferences=user_preferences,
            desired_places_per_day=min_places_per_day,
            category_modifiers=category_modifiers)

        # Темп поездки (CALM=5, MODERATE=8, ACTIVE=10) — это СТРОГАЯ
        # цель на каждый день: не меньше и не больше. Если для цели
        # не хватает мест в пуле, допускаем меньше (hard-limit пула).
        # Fallback: если профиль не задан, подстраиваемся под среднее
        # по выходу солвера, чтобы не допустить «тощих» дней.
        used_by_solver = sum(len(d) for d in optimized_days)
        target_per_day = int(min_places_per_day or 0)
        if target_per_day <= 0 and num_days > 0 and used_by_solver > 0:
            # Fallback, когда пользовательский темп неизвестен:
            # целимся в средний по солверу (не ниже 3).
            target_per_day = max(3, used_by_solver // num_days)
        if target_per_day > 0:
            # Шаг 1: trim — снимаем излишки с дней, где мест > target,
            # и перераспределяем их в дни, где мест < target.
            optimized_days = self._trim_over_target(
                optimized_days, target_per_day, user_preferences,
            )
            # Шаг 2: fill — добираем из оставшегося пула до target.
            optimized_days = self._enforce_min_places_per_day(
                places=places,
                optimized_days=optimized_days,
                hotel=hotel,
                min_places_per_day=target_per_day,
                user_preferences=user_preferences,
            )
            per_day_sizes = [len(d) for d in optimized_days]
            logger.info(
                'Tempo enforcement: target=%d, per_day=%s (requested=%s, solver_sum=%d)',
                target_per_day, per_day_sizes, min_places_per_day, used_by_solver,
            )

        # Внутридневное правило: кафе/рестораны не подряд (мин. 3 часа
        # между едой) и не более двух точек еды за день.
        optimized_days = self._space_out_food_places(
            optimized_days, meal_count=meal_count_per_day,
        )

        # Балансировка: если день оказался пустым, переносим в него
        # лучшее место из самого длинного дня (cross-day rebalance).
        optimized_days = self._rebalance_empty_days(optimized_days)

        # Перестраиваем all_points и матрицу под отобранные места
        selected_all_points = self._collect_all_points(hotel, optimized_days)
        selected_matrix = self._build_sub_matrix(selected_all_points, all_points, distance_matrix)

        day_plans, skipped_by_day = self._build_schedule(
            optimized_days=optimized_days,
            start_date=start_date,
            start_time=start_time,
            distance_matrix=selected_matrix,
            all_points=selected_all_points,
            hotel=hotel,
            return_skipped=True,
            end_time=effective_end_time)

        # Если какой-то день не влез по часам — пробуем перенести
        # отброшенные места в соседние дни с запасом по времени.
        if skipped_by_day:
            day_plans = await self._fallback_skipped_across_days(
                day_plans=day_plans,
                skipped_by_day=skipped_by_day,
                optimized_days=optimized_days,
                hotel=hotel,
                start_date=start_date,
                start_time=start_time,
                all_points_full=all_points,
                distance_matrix_full=distance_matrix,
                end_time=effective_end_time,
            )

        try:
            await self._add_route_geometry(day_plans, hotel)
        except ORSError as e:
            logger.warning(f'Could not get route geometry: {e}')
        plan = TravelPlan(
            destination=destination,
            hotel=hotel,
            days=day_plans,
            # Store inputs so replan_day can re-solve a single day later.
            candidates=list(places),
            user_preferences=dict(user_preferences) if user_preferences else None,
            food_preferences=dict(food_preferences) if food_preferences else None,
            hours_per_day=float(effective_hours_per_day),
            start_hour=int(start_hour if start_hour is not None else start_time.hour),
            end_hour=int(end_h_int),
            meal_count_per_day=int(meal_count_per_day),
        )

        # Surface compromises detected during planning. Done after plan
        # construction so we can inspect actual day sizes.
        self._collect_post_plan_notes(
            plan=plan,
            target_per_day=int(min_places_per_day or 0),
            skipped_by_day=skipped_by_day or {},
            notes=plan_notes,
        )
        plan.plan_notes = plan_notes

        # Метрика качества плана для клиента.
        plan_quality = self._compute_plan_quality(plan, min_places_per_day or 0)
        plan.quality_score = plan_quality['score']
        plan.quality_report = plan_quality

        logger.info(
            f'Plan generated: {plan.total_places} places, {plan.total_distance_km:.1f} km, '
            f'{plan.total_travel_time_min} min travel, quality={plan_quality["score"]:.2f}')
        return plan

    def _trim_over_target(
        self,
        optimized_days: List[List[Place]],
        target_per_day: int,
        user_preferences: Optional[Dict[str, float]] = None,
    ) -> List[List[Place]]:
        """Переносит излишки из дней > target в дни < target.

        Сохраняет полный пул мест: solver мог назначить одному дню много
        хороших мест, а соседний оставить пустым. Перетасовываем, чтобы
        каждый день был ровно на target (если позволяет общий пул).
        Слабейшие места по rank (rating + pref) уходят первыми.
        """
        JUNK_CATEGORIES = {'shopping', 'other'}

        def rank_score(p: Place) -> float:
            category = p.category.value if hasattr(p.category, 'value') else str(p.category)
            pref = (user_preferences or {}).get(category, 0.5)
            rating = p.rating or 0.0
            category_penalty = 0.3 if category in JUNK_CATEGORIES else 0.0
            return pref * 2.0 + rating - category_penalty

        # Повторяем, пока есть перегруз и недогруз одновременно.
        safety = len(optimized_days) * max(target_per_day, 1) * 2
        while safety > 0:
            over = [
                i for i, d in enumerate(optimized_days)
                if len(d) > target_per_day
            ]
            under = [
                i for i, d in enumerate(optimized_days)
                if len(d) < target_per_day
            ]
            if not over or not under:
                break
            # Источник — самый перегруженный день.
            src_i = max(over, key=lambda i: len(optimized_days[i]))
            # Приёмник — самый «тощий».
            dst_i = min(under, key=lambda i: len(optimized_days[i]))
            # Выбираем слабейшее место в src (minimum rank).
            src_day = optimized_days[src_i]
            weakest_idx = min(range(len(src_day)), key=lambda j: rank_score(src_day[j]))
            moved = src_day.pop(weakest_idx)
            optimized_days[dst_i].append(moved)
            safety -= 1
        return optimized_days

    def _enforce_min_places_per_day(
        self,
        places: List[Place],
        optimized_days: List[List[Place]],
        hotel: Place,
        min_places_per_day: int,
        user_preferences: Optional[Dict[str, float]] = None,
    ) -> List[List[Place]]:
        """Fill days up to ``min_places_per_day`` with quality gate.

        * Reject low-signal filler (no rating + category in junk set).
        * Apply quality threshold: rating < 3.0 and junk category → skip.
        * Never force-fill if a day is already full of quality content.
        """
        by_name: Dict[str, Place] = {p.name.strip().lower(): p for p in places}
        used = {
            p.name.strip().lower()
            for day in optimized_days
            for p in day
        }
        remaining = [
            p for key, p in by_name.items()
            if key not in used
        ]

        JUNK_CATEGORIES = {'shopping', 'other'}

        def is_quality_filler(p: Place) -> bool:
            category = p.category.value if hasattr(p.category, 'value') else str(p.category)
            rating = p.rating or 0.0
            if category in JUNK_CATEGORIES and rating < 4.0:
                return False
            if rating < 3.0 and category in JUNK_CATEGORIES:
                return False
            return True

        def rank_score(p: Place) -> float:
            category = p.category.value if hasattr(p.category, 'value') else str(p.category)
            pref = (user_preferences or {}).get(category, 0.5)
            rating = p.rating or 0.0
            category_penalty = 0.3 if category in JUNK_CATEGORIES else 0.0
            return pref * 2.0 + rating - category_penalty

        quality_pool = [p for p in remaining if is_quality_filler(p)]
        quality_pool.sort(key=lambda p: (-rank_score(p), p.visit_duration_min or 60))

        # NOTE: previously we also kept a "fallback pool" of low-quality
        # places (junk categories, no rating) and appended it after the
        # quality pool ran out. That produced filler like grocery stores,
        # clinics, and unrated OSM landmarks in the final itinerary. We
        # now refuse to dilute the plan: an understaffed day is logged as
        # a structured ``understaffed_day`` note instead.
        pool = quality_pool
        rem_idx = 0
        # Раздаём места всегда в день с наименьшим текущим размером —
        # это гарантирует, что изначально пустой день наполнится
        # раньше уже укомплектованных.
        while rem_idx < len(pool):
            target = min(enumerate(optimized_days), key=lambda kv: (len(kv[1]), kv[0]))[1]
            if len(target) >= min_places_per_day:
                break
            target.append(pool[rem_idx])
            rem_idx += 1

        low_density_days = [
            day_i for day_i, day in enumerate(optimized_days, 1)
            if len(day) < min_places_per_day
        ]
        if low_density_days:
            logger.info(
                'Low-density days after quality-gated fill: %s (target=%d)',
                low_density_days, min_places_per_day,
            )

        return optimized_days

    def _filter_low_signal_places(
        self, places: List[Place], num_days: int,
    ) -> List[Place]:
        """Выкидывает «шумные» POI из Overpass/OSM без рейтинга.

        Такие места (университеты, отдельные мечети/библиотеки, безликие
        площади и памятники) всплывают, когда 2GIS не набрал достаточно.
        Правила:
          * source in {overpass, osm} И rating отсутствует
          * category ∈ NOISY → убираем
        Плюс safety-net: если после фильтра мест меньше, чем num_days*6,
        возвращаем исходный список (лучше с мусором, чем пустой план).
        """
        NOISY_CATEGORIES = {
            'landmark', 'religious', 'shopping', 'transport', 'other',
        }
        OSM_SOURCES = {'overpass', 'osm'}

        def is_low_signal(p: Place) -> bool:
            src = (p.source or '').lower()
            if src not in OSM_SOURCES:
                return False
            if p.rating is not None and p.rating > 0:
                return False
            cat = p.category.value if hasattr(p.category, 'value') else str(p.category)
            return cat in NOISY_CATEGORIES

        kept = [p for p in places if not is_low_signal(p)]
        removed = len(places) - len(kept)
        min_needed = max(10, num_days * 6)
        if len(kept) < min_needed:
            logger.info(
                'low_signal filter kept %d < %d (num_days*6) — keeping originals (%d)',
                len(kept), min_needed, len(places),
            )
            return places
        if removed:
            logger.info(
                'low_signal filter removed %d places (rating-less OSM noise)',
                removed,
            )
        return kept

    def _filter_food_places(
        self, places: List[Place], food_preferences: Dict[str, bool],
    ) -> List[Place]:
        """Отбрасывает явно несовместимые с предпочтениями рестораны/кафе.

        Работает только как чёрный список по ключевым словам в названии
        и описании места — мы не располагаем надёжными тегами кухни на
        уровне POI-данных.
        """
        FOOD = {'restaurant', 'cafe'}
        # Слова, несовместимые с конкретным предпочтением.
        negative_map: Dict[str, List[str]] = {
            'vegetarian': ['steak', 'стейк', 'шашлык', 'мясо', 'bbq', 'grill', 'барбекю', 'kebab', 'шаурм'],
            'vegan': ['steak', 'стейк', 'шашлык', 'мясо', 'bbq', 'grill', 'kebab', 'шаурм', 'молочн', 'сырн'],
            'halal': ['свин', 'pork', 'бекон', 'bacon', 'ham', 'ветчин'],
        }
        bans: set[str] = set()
        for key, enabled in food_preferences.items():
            if not enabled:
                continue
            for w in negative_map.get(key, []):
                bans.add(w.lower())
        if not bans:
            return places

        filtered: List[Place] = []
        removed = 0
        for p in places:
            if p.category.value not in FOOD:
                filtered.append(p)
                continue
            hay = ' '.join([
                (p.name or ''),
                (getattr(p, 'description', '') or ''),
                ' '.join(getattr(p, 'rubrics', []) or []),
            ]).lower()
            if any(b in hay for b in bans):
                removed += 1
                continue
            filtered.append(p)
        if removed:
            logger.info('food_preferences filter removed %d places', removed)
        return filtered

    def _filter_non_tourist_places(
        self,
        places: List[Place],
        num_days: int,
    ) -> List[Place]:
        """Drop obvious service/medical/education POIs regardless of source."""
        kept: List[Place] = []
        removed = 0
        for p in places:
            category = p.category.value if hasattr(p.category, 'value') else str(p.category)
            text = ' '.join([
                p.name or '',
                p.address or '',
                p.description or '',
            ]).lower()
            if any(keyword in text for keyword in NON_TOURIST_PLACE_KEYWORDS):
                removed += 1
                continue
            # Transport/other are almost always low-value filler for tourism.
            if category in {'transport'}:
                removed += 1
                continue
            kept.append(p)

        if not kept:
            logger.info(
                'non-tourist filter removed all %d places — keeping originals as last resort',
                len(places),
            )
            return places
        if removed:
            logger.info('non-tourist filter removed %d places before planning', removed)
        return kept

    def _space_out_food_places(
        self, optimized_days: List[List[Place]], meal_count: int = 2,
    ) -> List[List[Place]]:
        """Перемешивает места внутри дня так, чтобы кафе/рестораны не шли подряд.

        Правила:
          * Максимум ``meal_count`` ``restaurant``/``cafe`` в день (1..3).
          * Равномерно распределяем их по дню (завтрак/обед/ужин).
          * Лишние точки еды перенесём в соседние дни, где их ещё меньше.
        """
        FOOD = {'restaurant', 'cafe'}
        meal_count = max(1, min(3, int(meal_count)))
        extra_food: List[Place] = []

        def arrange(non_food: List[Place], food: List[Place]) -> List[Place]:
            if not food:
                return list(non_food)
            n_food = len(food)
            n_non = len(non_food)
            # Равномерные позиции: food[k] идёт после ~(k+1)/(n_food+1) доли
            # культурной программы.
            out: List[Place] = []
            non_idx = 0
            for k in range(n_food):
                pos = max(0, int(round((k + 1) * n_non / (n_food + 1))))
                while non_idx < pos and non_idx < n_non:
                    out.append(non_food[non_idx])
                    non_idx += 1
                out.append(food[k])
            while non_idx < n_non:
                out.append(non_food[non_idx])
                non_idx += 1
            return out

        for day_i, day in enumerate(optimized_days):
            food = [p for p in day if p.category.value in FOOD]
            non_food = [p for p in day if p.category.value not in FOOD]
            if len(food) > meal_count:
                extra_food.extend(food[meal_count:])
                food = food[:meal_count]
            optimized_days[day_i] = arrange(non_food, food)

        # Отдаём excess-food в дни, где еды меньше лимита.
        for food_place in extra_food:
            target = None
            for day in optimized_days:
                food_count = sum(1 for p in day if p.category.value in FOOD)
                if food_count < meal_count:
                    target = day
                    break
            if target is None:
                continue
            non_food = [p for p in target if p.category.value not in FOOD]
            food = [p for p in target if p.category.value in FOOD] + [food_place]
            target[:] = arrange(non_food, food)

        return optimized_days

    def _rebalance_empty_days(
        self, optimized_days: List[List[Place]],
    ) -> List[List[Place]]:
        """Если день пуст, забираем одно место из самого «тяжёлого» дня."""
        while True:
            empty_idx = next(
                (i for i, d in enumerate(optimized_days) if not d), None,
            )
            if empty_idx is None:
                break
            # Ищем самый длинный день с >= 2 мест.
            donor_idx, donor_len = -1, 1
            for i, d in enumerate(optimized_days):
                if len(d) > donor_len:
                    donor_len = len(d)
                    donor_idx = i
            if donor_idx < 0:
                break
            optimized_days[empty_idx].append(optimized_days[donor_idx].pop())
        return optimized_days

    async def _fallback_skipped_across_days(
        self,
        day_plans: List[DayPlan],
        skipped_by_day: Dict[int, List[Place]],
        optimized_days: List[List[Place]],
        hotel: Place,
        start_date: date,
        start_time: time,
        all_points_full: List[Tuple[float, float]],
        distance_matrix_full: List[List[float]],
        end_time: Optional[time] = None,
    ) -> List[DayPlan]:
        """Пытается пересобрать дни с учётом мест, не влезших по часам.

        Простая стратегия: каждое пропущенное место пробуем поставить
        в конец дня, в который оно вписывается по окну работы и
        суммарному времени. Если находим — добавляем в optimized_days
        и перестраиваем расписание единожды.
        """
        moved = False
        for _, skipped_list in skipped_by_day.items():
            for place in skipped_list:
                # Ищем день, в котором visit укладывается в opening hours
                # и в оставшийся бюджет 10:00-22:00.
                best_day_idx = -1
                best_spare_min = -1
                for idx, plan in enumerate(day_plans):
                    if place in optimized_days[idx]:
                        # Уже числится в этом дне — пропускаем.
                        continue
                    open_t, close_t = resolve_opening_window(
                        place.opening_hours, place.category.value,
                    )
                    active_end = end_time if end_time is not None else DAY_WINDOW_END
                    used_min = plan.total_travel_time_min + plan.total_visit_time_min
                    spare_min = int((active_end.hour - DAY_WINDOW_START.hour) * 60 - used_min)
                    # Грубая эвристика: если места не меньше visit+60min на travel.
                    needed = (place.visit_duration_min or 60) + 60
                    if spare_min < needed:
                        continue
                    # opening hours должны пересекаться с рабочим окном.
                    if close_t <= DAY_WINDOW_START or open_t >= active_end:
                        continue
                    if spare_min > best_spare_min:
                        best_spare_min = spare_min
                        best_day_idx = idx
                if best_day_idx >= 0:
                    optimized_days[best_day_idx].append(place)
                    moved = True
                    logger.info(
                        'Cross-day fallback: "%s" moved to day %d (spare=%d min)',
                        place.name, best_day_idx + 1, best_spare_min,
                    )

        if not moved:
            return day_plans

        # Один полный пересбор расписания.
        selected_all_points = self._collect_all_points(hotel, optimized_days)
        selected_matrix = self._build_sub_matrix(
            selected_all_points, all_points_full, distance_matrix_full,
        )
        rebuilt = self._build_schedule(
            optimized_days=optimized_days,
            start_date=start_date,
            start_time=start_time,
            distance_matrix=selected_matrix,
            all_points=selected_all_points,
            hotel=hotel,
            return_skipped=False,
            end_time=end_time,
        )
        return rebuilt

    def _collect_post_plan_notes(
        self,
        plan: TravelPlan,
        target_per_day: int,
        skipped_by_day: Dict[int, List[Place]],
        notes: List[Dict[str, Any]],
    ) -> None:
        """Append structural warnings to ``notes`` based on the final plan.

        Detects:
          * empty days (zero activities)
          * understaffed days (fewer than ``target_per_day`` activities)
          * overflow (places dropped because the day window was too tight)
          * activities scheduled while the venue is likely closed
            (uses OpeningHoursTool when an ``opening_hours`` tag exists)
        """
        empty_days = [d.day_number for d in plan.days if not d.activities]
        if empty_days:
            notes.append({
                'type': 'empty_day',
                'severity': 'error',
                'message': (
                    f'Не удалось наполнить дни: {", ".join(map(str, empty_days))}. '
                    'В пуле кандидатов кончились качественные места — '
                    'попробуйте расширить интересы или уменьшить число дней.'
                ),
                'data': {'days': empty_days},
            })

        if target_per_day > 0:
            understaffed = [
                {'day': d.day_number, 'count': len(d.activities)}
                for d in plan.days
                if 0 < len(d.activities) < target_per_day
            ]
            if understaffed:
                day_strs = ', '.join(
                    f'{u["day"]} ({u["count"]} из {target_per_day})'
                    for u in understaffed
                )
                notes.append({
                    'type': 'understaffed_day',
                    'severity': 'warn',
                    'message': (
                        f'В дни {day_strs} удалось разместить меньше точек, '
                        f'чем рассчитано по темпу ({target_per_day}/день). '
                        'Не нашлось достаточно качественных мест по вашим интересам.'
                    ),
                    'data': {'target': target_per_day, 'days': understaffed},
                })

        # Overflow: solver assigned places that did not fit into the day's
        # active hour window. We surface this so the user knows we trimmed.
        overflow = [
            {'day': day_num, 'dropped': [p.name for p in places if p]}
            for day_num, places in (skipped_by_day or {}).items()
            if places
        ]
        if overflow:
            samples = []
            for entry in overflow[:3]:
                names = entry['dropped'][:3]
                if names:
                    samples.append(
                        f'день {entry["day"]}: {", ".join(names)}')
            notes.append({
                'type': 'overflow_day',
                'severity': 'warn',
                'message': (
                    'В некоторые дни не уместились все запланированные места: '
                    + '; '.join(samples)
                    + '. Можно увеличить дневное окно или сократить темп.'
                ),
                'data': {'days': overflow},
            })

        # Opening-hours sanity check for already-scheduled activities. We
        # don't pre-filter the candidate pool because OSM `opening_hours`
        # depends on weekday — a place closed on Monday may be the perfect
        # fit for a Wednesday slot. Instead, after the schedule is built,
        # we flag activities whose timing conflicts with their stated
        # hours so the agent (or user) can re-shuffle.
        try:
            from src.components.agent.infrastructure.tools.auxiliary.OpeningHoursTool import (
                OpeningHoursTool,
            )
            oh_tool = OpeningHoursTool()
        except Exception:
            oh_tool = None
        if oh_tool is not None:
            conflicts: List[Dict[str, Any]] = []
            for day in plan.days:
                for activity in day.activities:
                    raw = getattr(activity.place, 'opening_hours', None)
                    if not raw:
                        continue
                    when = datetime.combine(day.date, activity.start_time)
                    status = oh_tool.is_open_at(raw, when)
                    if status is False:
                        conflicts.append({
                            'day': day.day_number,
                            'place': activity.place.name,
                            'time': activity.start_time.strftime('%H:%M'),
                            'opening_hours': raw,
                        })
            if conflicts:
                preview = '; '.join(
                    f'день {c["day"]}: {c["place"]} ({c["time"]})'
                    for c in conflicts[:3]
                )
                notes.append({
                    'type': 'opening_hours_conflict',
                    'severity': 'warn',
                    'message': (
                        f'Возможно, эти места закрыты в назначенное время: {preview}. '
                        'Можно переставить день или уточнить часы работы.'
                    ),
                    'data': {'conflicts': conflicts},
                })

    def _compute_plan_quality(
        self, plan: TravelPlan, min_places_per_day: int,
    ) -> Dict[str, Any]:
        """Метрика качества: доля дней с целевым кол-вом мест, средний рейтинг, источники."""
        num_days = len(plan.days) or 1
        if min_places_per_day > 0:
            days_meeting = sum(
                1 for d in plan.days if len(d.activities) >= min_places_per_day
            )
            density_ratio = days_meeting / num_days
        else:
            density_ratio = 1.0 if all(d.activities for d in plan.days) else 0.0

        ratings: List[float] = []
        sources: Dict[str, int] = {}
        for d in plan.days:
            for a in d.activities:
                if a.place.rating:
                    ratings.append(a.place.rating)
                src = getattr(a.place, 'source', None) or 'unknown'
                sources[src] = sources.get(src, 0) + 1
        avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
        rating_ratio = min(avg_rating / 5.0, 1.0) if avg_rating else 0.0

        # Итоговый скор 0..1: 60% плотность, 40% рейтинг.
        score = round(0.6 * density_ratio + 0.4 * rating_ratio, 3)
        return {
            'score': score,
            'days_meeting_target': int(density_ratio * num_days),
            'total_days': num_days,
            'min_places_per_day': min_places_per_day,
            'avg_rating': round(avg_rating, 2),
            'source_breakdown': sources,
        }

    def _empty_plan(
            self,
            destination: str,
            hotel: Place,
            start_date: date,
            num_days: int) -> TravelPlan:
        days = [
            DayPlan(
                day_number=i +
                1,
                date=start_date +
                timedelta(
                    days=i)) for i in range(num_days)]
        return TravelPlan(destination=destination, hotel=hotel, days=days)

    def _collect_all_points(
            self, hotel: Place, daily_clusters: List[List[Place]]) -> List[Tuple[float, float]]:
        points = [(hotel.lat, hotel.lon)]
        for cluster in daily_clusters:
            for place in cluster:
                points.append((place.lat, place.lon))
        return points

    async def _get_ors_matrix(
            self, points: List[Tuple[float, float]]) -> List[List[float]]:
        result = await self.ors.get_matrix(points, profile=ORSClient.PROFILE_FOOT)
        durations = result['durations']
        return [[d / 60 if d else 0 for d in row] for row in durations]

    def _solve_orienteering(
        self,
        places: List[Place],
        distance_matrix: List[List[float]],
        num_days: int,
        hours_per_day: float,
        b_max_per_day: float,
        user_preferences: Optional[Dict[str, float]] = None,
        desired_places_per_day: Optional[int] = None,
        category_modifiers: Optional[Dict[str, float]] = None,
    ) -> List[List[Place]]:
        """Решает задачу командного ориентирования (TOP) и возвращает дневные маршруты."""
        # Строим OPPlaceParams для каждого кандидата (индекс 0 = depot/hotel)
        candidates = []
        for i, p in enumerate(places):
            candidates.append(OPPlaceParams(
                index=i + 1,  # +1 т.к. 0 = depot
                visit_duration_min=p.visit_duration_min,
                cost=float(p.price_level) if p.price_level else 2.0,
                rating=p.rating if p.rating is not None else 3.0,
                category=p.category.value,
            ))

        # Конфигурация с ограничениями из профиля пользователя
        config = OPConfig(
            t_max_per_day=hours_per_day * 60,
            b_max_per_day=b_max_per_day,
            desired_places_per_day=desired_places_per_day,
        )
        solver = OrienteeringSolver(config)

        solution = solver.solve(
            distance_matrix=distance_matrix,
            time_matrix=None,
            candidates=candidates,
            num_days=num_days,
            depot_idx=0,
            user_preferences=user_preferences,
            category_modifiers=category_modifiers,
        )

        # Конвертируем индексы обратно в объекты Place
        optimized: List[List[Place]] = []
        for route in solution.routes:
            day_places = []
            for idx in route:
                place_i = idx - 1  # обратно из индекса матрицы
                if 0 <= place_i < len(places):
                    day_places.append(places[place_i])
            optimized.append(day_places)

        logger.info(
            f'TOP solution: {sum(len(d) for d in optimized)}/{len(places)} '
            f'places selected, F*={solution.objective:.4f}'
        )
        return optimized

    def _build_sub_matrix(
        self,
        selected_points: List[Tuple[float, float]],
        all_points: List[Tuple[float, float]],
        full_matrix: List[List[float]],
    ) -> List[List[float]]:
        """Извлекает подматрицу расстояний для отобранных точек."""
        # Маппинг координат → индекс в полной матрице
        coord_to_full_idx: Dict[Tuple[float, float], int] = {}
        for i, pt in enumerate(all_points):
            coord_to_full_idx[pt] = i

        indices = []
        for pt in selected_points:
            full_idx = coord_to_full_idx.get(pt, 0)
            indices.append(full_idx)

        return [
            [full_matrix[i][j] for j in indices]
            for i in indices
        ]

    def _build_schedule(self,
                        optimized_days: List[List[Place]],
                        start_date: date,
                        start_time: time,
                        distance_matrix: List[List[float]],
                        all_points: List[Tuple[float,
                                               float]],
                        hotel: Place,
                        return_skipped: bool = False,
                        end_time: Optional[time] = None) -> Any:
        day_plans = []
        skipped_by_day: Dict[int, List[Place]] = {}
        place_to_idx = {(hotel.lat, hotel.lon): 0}
        idx = 1
        for day_places in optimized_days:
            for place in day_places:
                place_to_idx[place.lat, place.lon] = idx
                idx += 1
        # Earliest start is clamped into the 10:00–22:00 window.
        # Допускаем ранний старт дня, если пользователь явно указал
        # start_time < DAY_WINDOW_START (например, 07:00 для «ранней пташки»).
        effective_start = start_time
        # Активное окно дня: от пользовательского start_time до end_time (или 22:00).
        # Для opening-hours-резолвера это нижняя граница клампа.
        active_day_start = min(effective_start, DAY_WINDOW_START)
        active_day_end = end_time if end_time is not None else DAY_WINDOW_END
        for day_num, day_places in enumerate(optimized_days, 1):
            current_date = start_date + timedelta(days=day_num - 1)
            activities: List[Activity] = []
            current_time = datetime.combine(current_date, effective_start)
            day_end_dt = datetime.combine(current_date, active_day_end)
            prev_coords = (hotel.lat, hotel.lon)
            total_distance = 0.0
            total_travel_time = 0
            total_visit_time = 0
            skipped_places: List[Place] = []
            for place in day_places:
                prev_idx = place_to_idx.get(prev_coords, 0)
                curr_idx = place_to_idx.get((place.lat, place.lon), 0)
                travel_time_min = int(distance_matrix[prev_idx][curr_idx])
                travel_distance_km = travel_time_min / 60 * 5

                # Arrival at the venue and opening-hours adjustment.
                arrival_dt = current_time + timedelta(minutes=travel_time_min)
                open_t, close_t = resolve_opening_window(
                    place.opening_hours, place.category.value,
                    day_start=active_day_start, day_end=active_day_end,
                )
                earliest_open_dt = datetime.combine(current_date, open_t)
                latest_close_dt = datetime.combine(current_date, close_t)

                activity_start_dt = max(arrival_dt, earliest_open_dt)
                activity_start_dt = _round_up_datetime(activity_start_dt, TIME_ROUND_MINUTES)

                activity_end_dt = activity_start_dt + timedelta(minutes=place.visit_duration_min)
                activity_end_dt = _round_up_datetime(activity_end_dt, TIME_ROUND_MINUTES)

                # Hard constraints: inside day window AND venue hours.
                if activity_end_dt > day_end_dt or activity_end_dt > latest_close_dt:
                    skipped_places.append(place)
                    # Keep current_time where it was before travel so the
                    # next candidate does not pay the skipped travel cost.
                    continue

                activity = Activity(
                    place=place,
                    start_time=activity_start_dt.time(),
                    end_time=activity_end_dt.time(),
                    travel_time_from_prev_min=travel_time_min,
                    travel_distance_from_prev_km=travel_distance_km)
                activities.append(activity)
                total_distance += travel_distance_km
                total_travel_time += travel_time_min
                total_visit_time += place.visit_duration_min
                prev_coords = (place.lat, place.lon)
                current_time = activity_end_dt
            if activities:
                last_place = activities[-1].place
                last_idx = place_to_idx.get(
                    (last_place.lat, last_place.lon), 0)
                return_time = int(distance_matrix[last_idx][0])
                total_travel_time += return_time
                total_distance += return_time / 60 * 5
            if skipped_places:
                skipped_by_day[day_num] = skipped_places
                logger.info(
                    'Day %d: skipped %d places (window/hours): %s',
                    day_num, len(skipped_places),
                    ', '.join(p.name for p in skipped_places[:5]),
                )
            day_plan = DayPlan(
                day_number=day_num,
                date=current_date,
                activities=activities,
                total_distance_km=round(
                    total_distance,
                    2),
                total_travel_time_min=total_travel_time,
                total_visit_time_min=total_visit_time)
            day_plans.append(day_plan)
        if return_skipped:
            return day_plans, skipped_by_day
        return day_plans

    async def _add_route_geometry(
            self,
            day_plans: List[DayPlan],
            hotel: Place) -> None:
        for day_plan in day_plans:
            if not day_plan.activities:
                continue
            points = [(hotel.lat, hotel.lon)]
            for activity in day_plan.activities:
                points.append((activity.place.lat, activity.place.lon))
            points.append((hotel.lat, hotel.lon))
            try:
                result = await self.ors.get_directions(points)
                day_plan.route_geometry = json.dumps(
                    result.get('geometry', {}))
            except ORSError as e:
                logger.warning(
                    f'Could not get geometry for day {day_plan.day_number}: {e}')

    async def add_place_to_plan(
            self,
            plan: TravelPlan,
            place: Place,
            day_number: Optional[int] = None,
            user_preferences: Optional[Dict[str, float]] = None) -> TravelPlan:
        all_places = plan.get_all_places()
        all_places.append(place)
        return await self.generate_plan(destination=plan.destination, places=all_places, hotel=plan.hotel, start_date=plan.start_date, num_days=plan.num_days, user_preferences=user_preferences)

    async def remove_place_from_plan(
            self,
            plan: TravelPlan,
            place_name: str,
            user_preferences: Optional[Dict[str, float]] = None) -> TravelPlan:
        all_places = [p for p in plan.get_all_places(
        ) if p.name.lower() != place_name.lower()]
        return await self.generate_plan(destination=plan.destination, places=all_places, hotel=plan.hotel, start_date=plan.start_date, num_days=plan.num_days, user_preferences=user_preferences)

    async def geocode_hotel(self, address: str, city: str) -> Optional[Place]:
        full_address = f'{address}, {city}'
        coords = await self.ors.geocode(full_address)
        if not coords:
            return None
        return Place(
            name=address,
            lat=coords[0],
            lon=coords[1],
            category=PlaceCategory.HOTEL,
            visit_duration_min=0,
            address=full_address)

    async def replan_day(
        self,
        plan: TravelPlan,
        day_number: int,
        current_datetime: datetime,
        *,
        visited_place_names: Optional[List[str]] = None,
        additional_candidates: Optional[List[Place]] = None,
        category_modifiers: Optional[Dict[str, float]] = None,
    ) -> TravelPlan:
        """Regenerate a single day of the plan based on current context.

        The operation is a true re-optimisation: candidate POIs are rebuilt
        from the plan's stored candidate pool (+ optional new candidates),
        filtered by opening hours at ``current_datetime``, and re-solved with
        the orienteering solver constrained to the remaining hours of the day.
        Places in other days are preserved untouched. The resulting day
        replaces the old day_number slot, and aggregate stats are recomputed.
        """
        from src.components.agent.infrastructure.tools.auxiliary.OpeningHoursTool import (
            OpeningHoursTool,
        )

        target_day = plan.get_day(day_number)
        if target_day is None:
            raise ValueError(f'Day {day_number} not found in plan')

        visited_lower = {n.strip().lower() for n in (visited_place_names or []) if n}
        # Candidates for the replanned day: plan's saved candidate pool minus
        # places already scheduled in OTHER days (we don't want duplicates)
        # minus already-visited. Fall back to the day's own places when the
        # plan has no stored candidates (legacy plans created before replan).
        used_in_other_days = {
            activity.place.name.lower()
            for day in plan.days
            if day.day_number != day_number
            for activity in day.activities
        }
        pool: List[Place] = []
        seen_keys: set = set()

        def _add(place: Place) -> None:
            key = (place.name.lower(), round(place.lat, 5), round(place.lon, 5))
            if key in seen_keys:
                return
            if place.name.lower() in used_in_other_days:
                return
            if place.name.lower() in visited_lower:
                return
            seen_keys.add(key)
            pool.append(place)

        for p in plan.candidates or []:
            _add(p)
        # Fallback: if the plan was generated before candidates were stored,
        # use what is currently scheduled in this day as the baseline pool.
        if not pool:
            for activity in target_day.activities:
                _add(activity.place)
        for p in additional_candidates or []:
            _add(p)

        if not pool:
            logger.info('replan_day: candidate pool is empty, returning plan as-is')
            return plan

        # Filter POIs that are definitively closed at current_datetime. Places
        # without an `opening_hours` tag are kept (unknown → assume open).
        oh_tool = OpeningHoursTool()
        filtered = oh_tool.filter_places_by_time(
            (p.to_dict() for p in pool), current_datetime, keep_unknown=True,
        )
        # filter_places_by_time returns dicts — rebuild Place list preserving order.
        filtered_names = {d['name'] for d in filtered}
        pool = [p for p in pool if p.name in filtered_names]
        if not pool:
            logger.info('replan_day: all candidates closed at %s', current_datetime)
            return plan

        # Compute remaining time budget for the day. We honour the user's
        # configured end-of-day (``plan.end_hour``) rather than a hardcoded
        # default — that's the boundary the original plan was built against.
        try:
            plan_end_hour = int(getattr(plan, 'end_hour', None) or DAY_WINDOW_END.hour)
        except Exception:
            plan_end_hour = DAY_WINDOW_END.hour
        plan_end_hour = max(1, min(24, plan_end_hour))
        active_end = (
            time(plan_end_hour, 0) if plan_end_hour < 24 else time(23, 59)
        )
        day_end = datetime.combine(target_day.date, active_end)
        if current_datetime.tzinfo is not None and day_end.tzinfo is None:
            day_end = day_end.replace(tzinfo=current_datetime.tzinfo)
        remaining_seconds = (day_end - current_datetime).total_seconds()
        if remaining_seconds <= 30 * 60:
            logger.info('replan_day: not enough time left in the day to replan')
            return plan
        remaining_hours = remaining_seconds / 3600.0
        # Round start_time down to the nearest TIME_ROUND_MINUTES so schedule
        # building lines up cleanly.
        start_time = _round_up_datetime(
            current_datetime, TIME_ROUND_MINUTES,
        ).time().replace(second=0, microsecond=0)

        # ── (B) Adaptive meal slots ─────────────────────────────────────
        # Original `plan.meal_count_per_day` is sized for a full ~10h day.
        # When replanning the *evening* portion (e.g. starting at 14:00 →
        # 7h left) keeping 2 meals burns ~2h of the remaining window for
        # food alone. Scale meal count to the actual remaining window:
        #   ≥ 6h left → keep original count
        #   3..6h     → max 1 meal
        #   < 3h      → 0 meals (just sights)
        if remaining_hours >= 6:
            replan_meal_count = plan.meal_count_per_day
        elif remaining_hours >= 3:
            replan_meal_count = min(1, plan.meal_count_per_day)
        else:
            replan_meal_count = 0

        # ── (A) Carry over the original day's density target ───────────
        # The user already had N places planned for this day; expecting
        # only "what compute_points_per_day says for the leftover window"
        # surprises them. We aim for the *higher* of:
        #   (a) what was originally there
        #   (b) one place per ~1.5h of remaining time
        # so the rebuilt evening has comparable density to other days.
        from math import ceil
        original_density = target_day.places_count
        time_based_density = max(1, ceil(remaining_hours / 1.5))
        replan_target = max(original_density, time_based_density, 2)

        # ── (D) Top up the candidate pool when it's too small ──────────
        # After excluding already-scheduled and visited places the pool
        # can shrink below the density target — solver then can't find
        # 4 places to fit even though the city has them. Pull a fresh
        # batch via WebSearchTool when the pool is too thin.
        if len(pool) < max(5, replan_target * 2):
            try:
                from src.components.agent.infrastructure.tools.auxiliary.WebSearchTool import (
                    WebSearchTool,
                )
                search = WebSearchTool()
                extra = await search.search_places(
                    city=plan.destination,
                    interests=['достопримечательности', 'музей', 'парк'],
                    num_places=max(20, replan_target * 4),
                )
                if extra.get('success'):
                    used_keys = {(p.name.lower(), round(p.lat, 5), round(p.lon, 5))
                                 for p in pool}
                    used_keys.update({(n, 0, 0) for n in used_in_other_days})
                    used_keys.update({(n, 0, 0) for n in visited_lower})
                    for raw in extra.get('places') or []:
                        try:
                            cat_value = (raw.get('category') or 'other').lower()
                            place = Place(
                                name=raw['name'],
                                lat=float(raw['lat']),
                                lon=float(raw['lon']),
                                category=PlaceCategory(cat_value),
                                visit_duration_min=int(raw.get('visit_duration_min') or 60),
                                rating=raw.get('rating'),
                                price_level=raw.get('price_level'),
                                description=raw.get('description'),
                                address=raw.get('address'),
                                opening_hours=raw.get('opening_hours'),
                                source=raw.get('source'),
                            )
                        except (KeyError, ValueError):
                            continue
                        key = (place.name.lower(),
                               round(place.lat, 5),
                               round(place.lon, 5))
                        if key in used_keys:
                            continue
                        used_keys.add(key)
                        pool.append(place)
                        # Also persist new candidates back to the plan so
                        # subsequent replans can reuse them.
                        plan.candidates.append(place)
                    logger.info(
                        'replan_day: pool topped up to %d places via search_places',
                        len(pool),
                    )
            except Exception as e:  # noqa: BLE001 — best-effort top-up
                logger.warning('replan_day: pool top-up failed: %s', e)

        # Delegate to the standard single-day generator: num_days=1, everything
        # else inherited from the original plan so constraints stay consistent.
        one_day = await self.generate_plan(
            destination=plan.destination,
            places=pool,
            hotel=plan.hotel,
            start_date=target_day.date,
            num_days=1,
            hours_per_day=remaining_hours,
            start_time=start_time,
            user_preferences=plan.user_preferences,
            food_preferences=plan.food_preferences,
            meal_count_per_day=replan_meal_count,
            min_places_per_day=replan_target,
            start_hour=start_time.hour,
            end_hour=plan_end_hour,
            category_modifiers=category_modifiers,
        )
        if not one_day.days:
            return plan

        new_day = one_day.days[0]
        # Preserve the original day number and date so downstream consumers
        # (UI, exports) keep working.
        new_day.day_number = day_number
        new_day.date = target_day.date

        # Swap the day in place and recompute aggregates.
        plan.days = [
            new_day if d.day_number == day_number else d
            for d in plan.days
        ]
        plan._recalculate_stats()
        return plan
