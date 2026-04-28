from __future__ import annotations
import logging
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PlaceParams:
    """Параметры туристического объекта p_i = (x_i, y_i, v_i, c_i, r_i, k_i)."""
    index: int
    visit_duration_min: float      # v_i — время посещения
    cost: float                    # c_i — оценочная стоимость посещения
    rating: float                  # r_i — рейтинг объекта
    category: str                  # k_i — категория объекта
    quality: float = 0.0           # q_i — полезность (вычисляется)


@dataclass
class SAConfig:
    """Параметры алгоритма имитации отжига."""
    # Весовые коэффициенты целевой функции F(R)
    lambda_quality: float = 1.0     # λ₁ — вес полезности Q(R)
    lambda_distance: float = 0.3    # λ₂ — вес расстояния D(R)
    lambda_time: float = 0.2        # λ₃ — вес времени T(R)
    lambda_cost: float = 0.1        # λ₄ — вес стоимости C(R)

    # Коэффициенты полезности q_i = β₁·r_i + β₂·u_{k_i}
    beta_rating: float = 0.6        # β₁ — вес рейтинга
    beta_preference: float = 0.4    # β₂ — вес предпочтений пользователя

    # Параметры отжига
    initial_temp: float = 100.0     # T₀ — начальная температура
    cooling_rate: float = 0.995     # α — коэффициент охлаждения (T_{k+1} = α·T_k)
    min_temp: float = 0.01          # T_min — минимальная температура (критерий остановки)
    max_iterations: int = 10000     # максимальное число итераций

    # Ограничения
    t_max: float = float('inf')     # T_max — максимальное допустимое время (мин)
    b_max: float = float('inf')     # B_max — максимальный допустимый бюджет

    # Штрафной коэффициент за нарушение ограничений
    penalty_weight: float = 1000.0


class SimulatedAnnealingSolver:
    """
    Решение задачи маршрутизации методом имитации отжига (Simulated Annealing).

    Целевая функция:
        F(R) = λ₁·Q(R) − λ₂·D(R) − λ₃·T(R) − λ₄·C(R) → max

    где:
        Q(R) = Σ q_{i_k}                            — суммарная полезность маршрута
        D(R) = Σ d(i_k, i_{k+1})                    — суммарная длина маршрута
        T(R) = Σ t(i_k, i_{k+1}) + Σ v_{i_k}       — общее время маршрута
        C(R) = Σ c_{i_k}                            — суммарная стоимость маршрута

    Полезность объекта:
        q_i = β₁·r_i + β₂·u_{k_i}

    Ограничения:
        T(R) ≤ T_max,   C(R) ≤ B_max

    Критерий Метрополиса:
        P(ΔF, T) = exp(ΔF / T), если ΔF < 0
    """

    def __init__(self, config: Optional[SAConfig] = None):
        self.config = config or SAConfig()

    def solve(
        self,
        distance_matrix: List[List[float]],
        time_matrix: Optional[List[List[float]]],
        places: Optional[List[PlaceParams]] = None,
        user_preferences: Optional[Dict[str, float]] = None,
        start_idx: int = 0,
        return_to_start: bool = True,
    ) -> List[int]:
        """
        Решает задачу оптимальной маршрутизации методом имитации отжига.

        Args:
            distance_matrix: матрица расстояний d(i, j) в км
            time_matrix: матрица времени перемещения t(i, j) в мин.
                         Если None — вычисляется из distance_matrix (скорость 5 км/ч).
            places: параметры объектов [PlaceParams] (индекс 0 — стартовая точка).
                    Если None — оптимизация только по расстоянию.
            user_preferences: вектор предпочтений U = {category: u_j}.
                              Например: {"museum": 0.9, "park": 0.7, "restaurant": 0.5}.
            start_idx: индекс стартовой точки (отель).
            return_to_start: возвращаться ли в начальную точку.

        Returns:
            Оптимальный маршрут R* = [start, i₁, i₂, ..., start].
        """
        n = len(distance_matrix)
        if n <= 1:
            return list(range(n))
        if n == 2:
            return [0, 1, 0] if return_to_start else [0, 1]

        # Если нет time_matrix — вычисляем из расстояний (5 км/ч → мин)
        if time_matrix is None:
            time_matrix = [
                [d / 5.0 * 60 for d in row] for row in distance_matrix
            ]

        # Вычисляем полезность q_i для каждого объекта
        if places is not None:
            self._compute_qualities(places, user_preferences or {})

        cfg = self.config

        # Начальное решение — жадный Nearest Neighbor
        current_route = self._nearest_neighbor(distance_matrix, start_idx, n)

        # Добавляем возврат для вычисления F
        if return_to_start and current_route[-1] != start_idx:
            current_route.append(start_idx)

        current_f = self._objective(
            current_route, distance_matrix, time_matrix, places, cfg
        )

        best_route = list(current_route)
        best_f = current_f

        temperature = cfg.initial_temp
        iteration = 0
        accepted = 0
        rejected = 0

        while temperature > cfg.min_temp and iteration < cfg.max_iterations:
            # Генерация соседнего решения (2-opt swap)
            neighbor = self._generate_neighbor(
                current_route, start_idx, return_to_start
            )

            neighbor_f = self._objective(
                neighbor, distance_matrix, time_matrix, places, cfg
            )

            delta_f = neighbor_f - current_f

            # Критерий Метрополиса: P(ΔF, T) = exp(ΔF / T)
            if delta_f > 0:
                # Улучшение — принимаем безусловно
                current_route = neighbor
                current_f = neighbor_f
                accepted += 1
            else:
                # Ухудшение — принимаем с вероятностью P = exp(ΔF / T)
                probability = math.exp(delta_f / temperature)
                if random.random() < probability:
                    current_route = neighbor
                    current_f = neighbor_f
                    accepted += 1
                else:
                    rejected += 1

            # Обновляем лучшее решение
            if current_f > best_f:
                best_route = list(current_route)
                best_f = current_f

            # Геометрическое охлаждение: T_{k+1} = α · T_k
            temperature *= cfg.cooling_rate
            iteration += 1

        logger.debug(
            f'SA completed: {iteration} iterations, '
            f'accepted={accepted}, rejected={rejected}, '
            f'F(R*)={best_f:.4f}, T_final={temperature:.6f}'
        )

        return best_route

    def _compute_qualities(
        self,
        places: List[PlaceParams],
        user_preferences: Dict[str, float],
    ) -> None:
        """
        Вычисляет полезность каждого объекта:
            q_i = β₁ · r_i + β₂ · u_{k_i}
        """
        cfg = self.config
        for p in places:
            r_i = p.rating if p.rating is not None else 0.0
            u_ki = user_preferences.get(p.category, 0.5)
            p.quality = cfg.beta_rating * r_i + cfg.beta_preference * u_ki

    def _objective(
        self,
        route: List[int],
        distance_matrix: List[List[float]],
        time_matrix: List[List[float]],
        places: Optional[List[PlaceParams]],
        cfg: SAConfig,
    ) -> float:
        """
        Целевая функция:
            F(R) = λ₁·Q(R) − λ₂·D(R) − λ₃·T(R) − λ₄·C(R) − penalty

        Ограничения T(R) ≤ T_max, C(R) ≤ B_max учитываются через штраф.
        """
        m = len(route)
        if m < 2:
            return 0.0

        # D(R) = Σ d(i_k, i_{k+1}) — суммарная длина маршрута
        d_r = sum(
            distance_matrix[route[k]][route[k + 1]] for k in range(m - 1)
        )

        # T(R) = Σ t(i_k, i_{k+1}) + Σ v_{i_k} — общее время маршрута
        travel_time = sum(
            time_matrix[route[k]][route[k + 1]] for k in range(m - 1)
        )
        visit_time = 0.0
        if places is not None:
            for k in range(m):
                idx = route[k]
                if idx < len(places):
                    visit_time += places[idx].visit_duration_min
        t_r = travel_time + visit_time

        # C(R) = Σ c_{i_k} — суммарная стоимость маршрута
        c_r = 0.0
        if places is not None:
            for k in range(m):
                idx = route[k]
                if idx < len(places):
                    c_r += places[idx].cost

        # Q(R) = Σ q_{i_k} — суммарная полезность маршрута
        q_r = 0.0
        if places is not None:
            for k in range(m):
                idx = route[k]
                if idx < len(places):
                    q_r += places[idx].quality

        # F(R) = λ₁·Q(R) − λ₂·D(R) − λ₃·T(R) − λ₄·C(R)
        f = (
            cfg.lambda_quality * q_r
            - cfg.lambda_distance * d_r
            - cfg.lambda_time * t_r
            - cfg.lambda_cost * c_r
        )

        # Штрафы за нарушение ограничений
        penalty = 0.0
        if t_r > cfg.t_max:
            penalty += cfg.penalty_weight * (t_r - cfg.t_max)
        if c_r > cfg.b_max:
            penalty += cfg.penalty_weight * (c_r - cfg.b_max)

        return f - penalty

    def _nearest_neighbor(
        self,
        matrix: List[List[float]],
        start: int,
        n: int,
    ) -> List[int]:
        """Жадная эвристика ближайшего соседа для начального решения."""
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

    def _generate_neighbor(
        self,
        route: List[int],
        start_idx: int,
        return_to_start: bool,
    ) -> List[int]:
        """
        Генерация соседнего решения оператором 2-opt:
        переворот подсегмента маршрута между позициями i и j.
        Фиксирует начальную и (если нужно) конечную точку.
        """
        neighbor = list(route)

        # Определяем границы для мутации (не трогаем start и end)
        first_mutable = 1
        last_mutable = len(neighbor) - 2 if return_to_start else len(neighbor) - 1

        if last_mutable <= first_mutable:
            return neighbor

        i = random.randint(first_mutable, last_mutable - 1)
        j = random.randint(i + 1, last_mutable)

        # 2-opt: переворачиваем сегмент [i, j]
        neighbor[i:j + 1] = reversed(neighbor[i:j + 1])

        return neighbor

    def calculate_route_metrics(
        self,
        route: List[int],
        distance_matrix: List[List[float]],
        time_matrix: Optional[List[List[float]]],
        places: Optional[List[PlaceParams]],
    ) -> Dict[str, float]:
        """Рассчитывает все метрики маршрута для анализа."""
        if time_matrix is None:
            time_matrix = [
                [d / 5.0 * 60 for d in row] for row in distance_matrix
            ]

        m = len(route)

        d_r = sum(
            distance_matrix[route[k]][route[k + 1]] for k in range(m - 1)
        )
        travel_time = sum(
            time_matrix[route[k]][route[k + 1]] for k in range(m - 1)
        )
        visit_time = 0.0
        cost = 0.0
        quality = 0.0

        if places is not None:
            seen = set()
            for k in range(m):
                idx = route[k]
                if idx < len(places) and idx not in seen:
                    visit_time += places[idx].visit_duration_min
                    cost += places[idx].cost
                    quality += places[idx].quality
                    seen.add(idx)

        return {
            'distance_km': d_r,
            'travel_time_min': travel_time,
            'visit_time_min': visit_time,
            'total_time_min': travel_time + visit_time,
            'total_cost': cost,
            'total_quality': quality,
        }
