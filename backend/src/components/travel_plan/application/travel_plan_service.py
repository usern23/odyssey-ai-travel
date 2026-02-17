from __future__ import annotations
import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from src.components.travel_plan.domain.entities import Activity, DayPlan, Place, PlaceCategory, TravelPlan
from src.components.travel_plan.infrastructure.ors_client import ORSClient, ORSError
from src.components.travel_plan.application.tsp_solver import TSPSolver, build_distance_matrix_haversine, estimate_walking_time
from src.components.travel_plan.application.cluster_service import ClusterService
logger = logging.getLogger(__name__)


class TravelPlanService:
    DEFAULT_START_TIME = time(9, 0)
    DEFAULT_END_TIME = time(21, 0)
    DEFAULT_LUNCH_TIME = time(13, 0)
    DEFAULT_DINNER_TIME = time(19, 0)

    def __init__(self, ors_client: Optional[ORSClient] = None):
        self.ors = ors_client or ORSClient()
        self.tsp = TSPSolver()
        self.cluster = ClusterService()

    async def generate_plan(
            self,
            destination: str,
            places: List[Place],
            hotel: Place,
            start_date: date,
            num_days: int,
            hours_per_day: float = 8.0,
            start_time: time = DEFAULT_START_TIME,
            use_real_distances: bool = True) -> TravelPlan:
        logger.info(
            f'Generating plan for {destination}: {
                len(places)} places, {num_days} days')
        if not places:
            return self._empty_plan(destination, hotel, start_date, num_days)
        daily_clusters = self.cluster.cluster_with_time_budget(
            places=places, num_days=num_days, hours_per_day=hours_per_day)
        logger.debug(
            f'Clustered into {len(daily_clusters)} days: {[len(c) for c in daily_clusters]}')
        all_points = self._collect_all_points(hotel, daily_clusters)
        if use_real_distances:
            try:
                distance_matrix = await self._get_ors_matrix(all_points)
            except ORSError as e:
                logger.warning(f'ORS Matrix failed, using haversine: {e}')
                distance_matrix = build_distance_matrix_haversine(all_points)
        else:
            distance_matrix = build_distance_matrix_haversine(all_points)
        optimized_days = self._optimize_daily_routes(
            hotel=hotel,
            daily_clusters=daily_clusters,
            distance_matrix=distance_matrix,
            all_points=all_points)
        day_plans = self._build_schedule(
            optimized_days=optimized_days,
            start_date=start_date,
            start_time=start_time,
            distance_matrix=distance_matrix,
            all_points=all_points,
            hotel=hotel)
        try:
            await self._add_route_geometry(day_plans, hotel)
        except ORSError as e:
            logger.warning(f'Could not get route geometry: {e}')
        plan = TravelPlan(destination=destination, hotel=hotel, days=day_plans)
        logger.info(
            f'Plan generated: {
                plan.total_places} places, {
                plan.total_distance_km:.1f} km, {
                plan.total_travel_time_min} min travel')
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

    def _optimize_daily_routes(self,
                               hotel: Place,
                               daily_clusters: List[List[Place]],
                               distance_matrix: List[List[float]],
                               all_points: List[Tuple[float,
                                                      float]]) -> List[List[Place]]:
        optimized = []
        place_to_idx = {0: 0}
        idx = 1
        for cluster in daily_clusters:
            for place in cluster:
                place_to_idx[id(place)] = idx
                idx += 1
        for day_places in daily_clusters:
            if not day_places:
                optimized.append([])
                continue
            if len(day_places) == 1:
                optimized.append(day_places)
                continue
            indices = [0] + [place_to_idx[id(p)] for p in day_places]
            sub_matrix = [[distance_matrix[i][j]
                           for j in indices] for i in indices]
            route = self.tsp.solve(
                sub_matrix, start_idx=0, return_to_start=True)
            ordered_places = []
            for route_idx in route:
                if route_idx == 0:
                    continue
                place_idx = route_idx - 1
                if 0 <= place_idx < len(day_places):
                    ordered_places.append(day_places[place_idx])
            optimized.append(ordered_places)
        return optimized

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
                    f'Could not get geometry for day {
                        day_plan.day_number}: {e}')

    async def add_place_to_plan(
            self,
            plan: TravelPlan,
            place: Place,
            day_number: Optional[int] = None) -> TravelPlan:
        all_places = plan.get_all_places()
        all_places.append(place)
        return await self.generate_plan(destination=plan.destination, places=all_places, hotel=plan.hotel, start_date=plan.start_date, num_days=plan.num_days)

    async def remove_place_from_plan(
            self,
            plan: TravelPlan,
            place_name: str) -> TravelPlan:
        all_places = [p for p in plan.get_all_places(
        ) if p.name.lower() != place_name.lower()]
        return await self.generate_plan(destination=plan.destination, places=all_places, hotel=plan.hotel, start_date=plan.start_date, num_days=plan.num_days)

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
