from __future__ import annotations
import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from src.components.travel_plan.domain.entities import Activity, DayPlan, Place, PlaceCategory, TravelPlan
from src.components.travel_plan.infrastructure.ors_client import ORSClient, ORSError
from src.components.travel_plan.application.tsp_solver import TSPSolver, build_distance_matrix_haversine, estimate_walking_time
from src.components.travel_plan.application.orienteering_solver import OrienteeringSolver, OPConfig, OPPlaceParams
logger = logging.getLogger(__name__)


class TravelPlanService:
    DEFAULT_START_TIME = time(9, 0)
    DEFAULT_END_TIME = time(21, 0)
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
            user_preferences: Optional[Dict[str, float]] = None) -> TravelPlan:
        logger.info(
            f'Generating plan for {destination}: {len(places)} places, {num_days} days')
        if not places:
            return self._empty_plan(destination, hotel, start_date, num_days)

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
            hours_per_day=hours_per_day,
            b_max_per_day=b_max_per_day,
            user_preferences=user_preferences)

        # Перестраиваем all_points и матрицу под отобранные места
        selected_all_points = self._collect_all_points(hotel, optimized_days)
        selected_matrix = self._build_sub_matrix(selected_all_points, all_points, distance_matrix)

        day_plans = self._build_schedule(
            optimized_days=optimized_days,
            start_date=start_date,
            start_time=start_time,
            distance_matrix=selected_matrix,
            all_points=selected_all_points,
            hotel=hotel)
        try:
            await self._add_route_geometry(day_plans, hotel)
        except ORSError as e:
            logger.warning(f'Could not get route geometry: {e}')
        plan = TravelPlan(destination=destination, hotel=hotel, days=day_plans)
        logger.info(
            f'Plan generated: {plan.total_places} places, {plan.total_distance_km:.1f} km, {plan.total_travel_time_min} min travel')
        return plan

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
        )
        solver = OrienteeringSolver(config)

        solution = solver.solve(
            distance_matrix=distance_matrix,
            time_matrix=None,
            candidates=candidates,
            num_days=num_days,
            depot_idx=0,
            user_preferences=user_preferences,
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
                        hotel: Place) -> List[DayPlan]:
        day_plans = []
        place_to_idx = {(hotel.lat, hotel.lon): 0}
        idx = 1
        for day_places in optimized_days:
            for place in day_places:
                place_to_idx[place.lat, place.lon] = idx
                idx += 1
        for day_num, day_places in enumerate(optimized_days, 1):
            current_date = start_date + timedelta(days=day_num - 1)
            activities = []
            current_time = datetime.combine(current_date, start_time)
            prev_coords = (hotel.lat, hotel.lon)
            total_distance = 0.0
            total_travel_time = 0
            total_visit_time = 0
            for place in day_places:
                prev_idx = place_to_idx.get(prev_coords, 0)
                curr_idx = place_to_idx.get((place.lat, place.lon), 0)
                travel_time_min = int(distance_matrix[prev_idx][curr_idx])
                travel_distance_km = travel_time_min / 60 * 5
                current_time += timedelta(minutes=travel_time_min)
                activity_start = current_time.time()
                current_time += timedelta(minutes=place.visit_duration_min)
                activity_end = current_time.time()
                activity = Activity(
                    place=place,
                    start_time=activity_start,
                    end_time=activity_end,
                    travel_time_from_prev_min=travel_time_min,
                    travel_distance_from_prev_km=travel_distance_km)
                activities.append(activity)
                total_distance += travel_distance_km
                total_travel_time += travel_time_min
                total_visit_time += place.visit_duration_min
                prev_coords = (place.lat, place.lon)
            if day_places:
                last_idx = place_to_idx.get(
                    (day_places[-1].lat, day_places[-1].lon), 0)
                return_time = int(distance_matrix[last_idx][0])
                total_travel_time += return_time
                total_distance += return_time / 60 * 5
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
