from __future__ import annotations
import logging
import math
from typing import List, Optional, Tuple
logger = logging.getLogger(__name__)


class TSPSolver:

    def solve(self,
              distance_matrix: List[List[float]],
              start_idx: int = 0,
              return_to_start: bool = True) -> List[int]:
        n = len(distance_matrix)
        if n <= 1:
            return list(range(n))
        if n == 2:
            return [0, 1] if not return_to_start else [0, 1, 0]
        route = self._nearest_neighbor(distance_matrix, start_idx)
        route = self._two_opt(distance_matrix, route)
        if return_to_start and route[-1] != start_idx:
            route.append(start_idx)
        logger.debug(f'TSP solved for {n} points, route length: {len(route)}')
        return route

    def _nearest_neighbor(self,
                          matrix: List[List[float]],
                          start: int) -> List[int]:
        n = len(matrix)
        visited = [False] * n
        route = [start]
        visited[start] = True
        current = start
        for _ in range(n - 1):
            best_next = -1
            best_dist = float('inf')
            for j in range(n):
                if not visited[j] and matrix[current][j] < best_dist:
                    best_dist = matrix[current][j]
                    best_next = j
            if best_next >= 0:
                route.append(best_next)
                visited[best_next] = True
                current = best_next
        return route

    def _two_opt(self,
                 matrix: List[List[float]],
                 route: List[int],
                 max_iterations: int = 100) -> List[int]:
        n = len(route)
        if n < 4:
            return route
        improved = True
        iteration = 0
        while improved and iteration < max_iterations:
            improved = False
            iteration += 1
            for i in range(n - 2):
                for j in range(i + 2, n):
                    if j == i + 1:
                        continue
                    delta = self._two_opt_delta(matrix, route, i, j)
                    if delta < -1e-10:
                        route[i + 1:j + 1] = reversed(route[i + 1:j + 1])
                        improved = True
        logger.debug(f'2-opt completed in {iteration} iterations')
        return route

    def _two_opt_delta(self,
                       matrix: List[List[float]],
                       route: List[int],
                       i: int,
                       j: int) -> float:
        n = len(route)
        a, b = (route[i], route[i + 1])
        c, d = (route[j], route[(j + 1) % n])
        current = matrix[a][b] + matrix[c][d]
        new = matrix[a][c] + matrix[b][d]
        return new - current

    def calculate_route_distance(self,
                                 matrix: List[List[float]],
                                 route: List[int]) -> float:
        total = 0.0
        for i in range(len(route) - 1):
            total += matrix[route[i]][route[i + 1]]
        return total

    def solve_with_constraints(self,
                               distance_matrix: List[List[float]],
                               start_idx: int = 0,
                               fixed_positions: Optional[dict] = None,
                               must_visit_together: Optional[List[Tuple[int,
                                                                        int]]] = None) -> List[int]:
        return self.solve(distance_matrix, start_idx)


def haversine_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float) -> float:
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * \
        math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def build_distance_matrix_haversine(
        points: List[Tuple[float, float]]) -> List[List[float]]:
    n = len(points)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dist = haversine_distance(
                points[i][0],
                points[i][1],
                points[j][0],
                points[j][1])
            matrix[i][j] = dist
            matrix[j][i] = dist
    return matrix


def estimate_walking_time(distance_km: float) -> float:
    return distance_km / 5.0 * 60
