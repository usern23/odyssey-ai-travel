from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Структуры данных
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class OPPlaceParams:
    """Параметры кандидата p_i = (idx, v_i, c_i, r_i, k_i) для задачи ориентирования."""
    index: int                      # глобальный индекс в матрице расстояний
    visit_duration_min: float       # v_i — время посещения (мин)
    cost: float                     # c_i — оценочная стоимость
    rating: float                   # r_i — рейтинг объекта (0–5)
    category: str                   # k_i — категория объекта
    quality: float = 0.0            # q_i — вычисленная полезность


@dataclass
class OPConfig:
    """Конфигурация решателя задачи командного ориентирования."""

    # Весовые коэффициенты целевой функции F(R)
    lambda_quality: float = 1.0     # λ₁ — вес полезности Q(R)
    lambda_distance: float = 0.3    # λ₂ — вес расстояния D(R)
    lambda_time: float = 0.2        # λ₃ — вес времени T(R)
    lambda_cost: float = 0.1        # λ₄ — вес стоимости C(R)

    # Коэффициенты полезности q_i = β₁·r̂_i + β₂·u_{k_i}
    beta_rating: float = 0.6        # β₁ — вес рейтинга
    beta_preference: float = 0.4    # β₂ — вес предпочтений пользователя

    # Параметры алгоритма имитации отжига
    initial_temp: float = 100.0     # T₀ — начальная температура
    cooling_rate: float = 0.995     # α — геометрическое охлаждение: T_{k+1} = α·T_k
    min_temp: float = 0.01          # T_min — критерий остановки
    max_iterations: int = 15000     # максимальное число итераций

    # Ограничения на один день
    t_max_per_day: float = 480.0    # T_max — максимальное время в день (мин)
    b_max_per_day: float = float('inf')  # B_max — максимальный бюджет в день

    # Штрафной коэффициент
    penalty_weight: float = 1000.0

    # Целевое количество мест в день + штраф за отклонение.
    # Высокий коэффициент делает темп поездки (CALM/MODERATE/ACTIVE)
    # жёсткой целью: solver предпочтёт докрутить день до target_per_day
    # даже ценой небольшого падения суммарной награды за рейтинги.
    desired_places_per_day: Optional[int] = None
    desired_places_penalty: float = 30.0

    # Вероятности выбора оператора соседства
    prob_2opt: float = 0.30         # p₁ — 2-opt (реверс сегмента)
    prob_insert: float = 0.25       # p₂ — вставка нового места
    prob_remove: float = 0.15       # p₃ — удаление места
    prob_swap: float = 0.20         # p₄ — обмен посещённого и непосещённого
    prob_move: float = 0.10         # p₅ — перемещение между днями


@dataclass
class OPSolution:
    """Решение задачи командного ориентирования."""
    routes: List[List[int]]         # R = {R₁, …, R_D} — маршруты по дням
    unvisited: List[int]            # множество непосещённых кандидатов
    objective: float = 0.0          # F(R) — значение целевой функции


# ═══════════════════════════════════════════════════════════════════════
#  Решатель задачи командного ориентирования (Team Orienteering Problem)
# ═══════════════════════════════════════════════════════════════════════

class OrienteeringSolver:
    """
    Решение задачи командного ориентирования (Team Orienteering Problem)
    методом имитации отжига (Simulated Annealing).

    В отличие от классической задачи коммивояжёра (TSP), решатель
    выбирает КАКИЕ объекты посетить из множества кандидатов,
    распределяет их по дням и оптимизирует порядок обхода.

    Целевая функция (суммарная по всем дням):
        F(R) = Σ_d F(R_d) → max

    Целевая функция одного дня:
        F(R_d) = λ₁·Q(R_d) − λ₂·D(R_d) − λ₃·T(R_d) − λ₄·C(R_d) → max

    где:
        Q(R_d) = Σ_{i ∈ R_d} q_i              — суммарная полезность
        D(R_d) = Σ d(p_k, p_{k+1})            — суммарное расстояние
        T(R_d) = Σ t(p_k, p_{k+1}) + Σ v_i   — суммарное время
        C(R_d) = Σ_{i ∈ R_d} c_i              — суммарная стоимость

    Полезность объекта:
        q_i = β₁ · r̂_i + β₂ · u_{k_i}
        где r̂_i = r_i / 5 — нормализованный рейтинг

    Ограничения (на каждый день d):
        T(R_d) ≤ T_max,   C(R_d) ≤ B_max

    Операторы соседства:
        1. 2-opt    — реверс сегмента внутри дня     (улучшение маршрута)
        2. Insert   — вставка нового объекта в день   (расширение)
        3. Remove   — удаление объекта из дня          (сокращение)
        4. Swap     — обмен посещённого и непосещённого (замена)
        5. Move     — перемещение объекта между днями   (балансировка)

    Критерий Метрополиса:
        P(ΔF, T_k) = exp(ΔF / T_k), если ΔF < 0
    """

    def __init__(self, config: Optional[OPConfig] = None):
        self.config = config or OPConfig()

    # ─── Основной метод ───────────────────────────────────────────────

    def solve(
        self,
        distance_matrix: List[List[float]],
        time_matrix: Optional[List[List[float]]],
        candidates: List[OPPlaceParams],
        num_days: int,
        depot_idx: int = 0,
        user_preferences: Optional[Dict[str, float]] = None,
        category_modifiers: Optional[Dict[str, float]] = None,
    ) -> OPSolution:
        """
        Решает задачу командного ориентирования методом имитации отжига.

        Args:
            distance_matrix: матрица расстояний d(i, j), включая depot (км)
            time_matrix: матрица времени t(i, j) в мин.
                         Если None — оценка по расстоянию (5 км/ч).
            candidates: список объектов-кандидатов (без depot)
            num_days: количество дней D
            depot_idx: индекс отеля (depot) в матрице
            user_preferences: вектор предпочтений U = {категория: u_j ∈ [0, 1]}
            category_modifiers: мультипликаторы полезности по категориям,
                например, штрафы за плохую погоду для outdoor-POI. Применяются
                после базового расчёта q_i: q_i ← q_i · m_{k_i}. По умолчанию 1.0.

        Returns:
            OPSolution — оптимальные маршруты R* = {R₁*, …, R_D*}
        """
        if not candidates:
            return OPSolution(
                routes=[[] for _ in range(num_days)],
                unvisited=[],
                objective=0.0,
            )

        # Если нет time_matrix — оценка: пешком 5 км/ч
        if time_matrix is None:
            time_matrix = [
                [d / 5.0 * 60 for d in row] for row in distance_matrix
            ]

        # Вычисляем полезность q_i для каждого кандидата
        self._compute_qualities(candidates, user_preferences or {}, category_modifiers)

        # Индекс для быстрого доступа к параметрам по глобальному индексу
        place_by_idx: Dict[int, OPPlaceParams] = {
            p.index: p for p in candidates
        }

        cfg = self.config

        # Нормализационные масштабы для сопоставимости компонентов F(R)
        # D̃ = D / d_max,  T̃ = T / T_ref,  C̃ = C / C_ref
        n = len(distance_matrix)
        self._d_ref = max(
            (distance_matrix[i][j] for i in range(n) for j in range(n) if i != j),
            default=1.0,
        )
        self._d_ref = max(self._d_ref, 0.01)
        self._t_ref = cfg.t_max_per_day if cfg.t_max_per_day < float('inf') else 480.0
        self._c_ref = (
            cfg.b_max_per_day if cfg.b_max_per_day < float('inf')
            else max((p.cost for p in candidates), default=1.0) * len(candidates) / max(num_days, 1)
        )
        self._c_ref = max(self._c_ref, 0.01)

        # ── Шаг 1: Жадное начальное решение ──
        solution = self._greedy_initial(
            candidates, num_days, depot_idx, time_matrix, place_by_idx, cfg,
        )
        solution.objective = self._total_objective(
            solution, depot_idx, distance_matrix, time_matrix, place_by_idx, cfg,
        )

        best = OPSolution(
            routes=[list(r) for r in solution.routes],
            unvisited=list(solution.unvisited),
            objective=solution.objective,
        )

        # ── Шаг 2: Имитация отжига ──
        temperature = cfg.initial_temp
        iteration = 0

        while temperature > cfg.min_temp and iteration < cfg.max_iterations:
            # Выбираем случайный оператор и генерируем соседнее решение
            neighbor = self._apply_random_operator(
                solution, depot_idx, distance_matrix, time_matrix,
                place_by_idx, cfg,
            )

            if neighbor is None:
                iteration += 1
                temperature *= cfg.cooling_rate
                continue

            neighbor.objective = self._total_objective(
                neighbor, depot_idx, distance_matrix, time_matrix,
                place_by_idx, cfg,
            )

            delta_f = neighbor.objective - solution.objective

            # Критерий Метрополиса: P(ΔF, T) = exp(ΔF / T)
            if delta_f > 0 or random.random() < math.exp(delta_f / temperature):
                solution = neighbor

            # Обновляем лучшее найденное решение
            if solution.objective > best.objective:
                best = OPSolution(
                    routes=[list(r) for r in solution.routes],
                    unvisited=list(solution.unvisited),
                    objective=solution.objective,
                )

            # Геометрическое охлаждение: T_{k+1} = α · T_k
            temperature *= cfg.cooling_rate
            iteration += 1

        # ── Детальные метрики для экспериментального анализа ──
        visited_count = sum(len(r) for r in best.routes)
        total_count = len(candidates)
        total_q = 0.0
        total_d = 0.0
        total_t = 0.0
        total_c = 0.0
        pref_sum = 0.0
        prefs = user_preferences or {}
        for route in best.routes:
            if not route:
                continue
            full_path = [depot_idx] + route + [depot_idx]
            total_q += sum(place_by_idx[i].quality for i in route if i in place_by_idx)
            total_d += sum(
                distance_matrix[full_path[k]][full_path[k + 1]]
                for k in range(len(full_path) - 1)
            )
            travel = sum(
                time_matrix[full_path[k]][full_path[k + 1]]
                for k in range(len(full_path) - 1)
            )
            visit = sum(place_by_idx[i].visit_duration_min for i in route if i in place_by_idx)
            total_t += travel + visit
            total_c += sum(place_by_idx[i].cost for i in route if i in place_by_idx)
            pref_sum += sum(prefs.get(place_by_idx[i].category, 0.5) for i in route if i in place_by_idx)

        pref_avg = pref_sum / max(visited_count, 1)
        t_violated = any(
            sum(time_matrix[([depot_idx] + r + [depot_idx])[k]][([depot_idx] + r + [depot_idx])[k + 1]]
                for k in range(len(r) + 1))
            + sum(place_by_idx[i].visit_duration_min for i in r if i in place_by_idx)
            > cfg.t_max_per_day
            for r in best.routes if r
        )
        c_violated = any(
            sum(place_by_idx[i].cost for i in r if i in place_by_idx) > cfg.b_max_per_day
            for r in best.routes if r
        )

        logger.info(
            f'OP solved: {iteration} iters | '
            f'coverage={visited_count}/{total_count} ({visited_count / max(total_count, 1) * 100:.0f}%) | '
            f'Q={total_q:.3f} | D={total_d:.2f}km | T={total_t:.0f}min | C={total_c:.1f} | '
            f'pref_match={pref_avg:.3f} | constraints={"OK" if not t_violated and not c_violated else "VIOLATED"} | '
            f'F*={best.objective:.4f}'
        )

        return best

    # ─── Вычисление полезности ────────────────────────────────────────

    def _compute_qualities(
        self,
        candidates: List[OPPlaceParams],
        user_preferences: Dict[str, float],
        category_modifiers: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Вычисляет полезность каждого кандидата:
            q_i = β₁ · r̂_i + β₂ · u_{k_i}
        где r̂_i = r_i / 5 — нормализация рейтинга к диапазону [0, 1].

        При наличии `category_modifiers` (мультипликаторов по категориям)
        финальное значение умножается на соответствующий коэффициент
        (например, для учёта штрафа за плохую погоду на outdoor-POI).
        """
        cfg = self.config
        modifiers = category_modifiers or {}
        for p in candidates:
            r_norm = (p.rating / 5.0) if p.rating else 0.0
            u_ki = user_preferences.get(p.category, 0.5)
            quality = cfg.beta_rating * r_norm + cfg.beta_preference * u_ki
            modifier = modifiers.get(p.category, 1.0)
            p.quality = quality * modifier

    # ─── Жадное начальное решение ─────────────────────────────────────

    def _greedy_initial(
        self,
        candidates: List[OPPlaceParams],
        num_days: int,
        depot_idx: int,
        time_matrix: List[List[float]],
        place_by_idx: Dict[int, OPPlaceParams],
        cfg: OPConfig,
    ) -> OPSolution:
        """
        Жадная конструктивная эвристика с балансировкой дней:

        1. Сортируем кандидатов по q_i / v_i (полезность на минуту).
        2. Для каждого кандидата выбираем день с НАИМЕНЬШЕЙ текущей
           нагрузкой (day_time[d]) — это распределяет качество по всем
           дням вместо того, чтобы забивать первые дни и оставлять
           последние пустыми.
        3. Если в наименее загруженный день место не влезает по
           T_max/B_max — пробуем остальные дни по возрастанию нагрузки.
        """
        sorted_candidates = sorted(
            candidates,
            key=lambda p: p.quality / max(p.visit_duration_min, 1),
            reverse=True,
        )

        routes: List[List[int]] = [[] for _ in range(num_days)]
        day_time = [0.0] * num_days
        day_cost = [0.0] * num_days
        unvisited: List[int] = []

        for place in sorted_candidates:
            # Дни, отсортированные по возрастанию текущей нагрузки.
            day_order = sorted(range(num_days), key=lambda d: (day_time[d], day_cost[d], d))
            inserted = False
            for d in day_order:
                last_idx = routes[d][-1] if routes[d] else depot_idx
                travel_to = time_matrix[last_idx][place.index]
                travel_back = time_matrix[place.index][depot_idx]
                current_return = (
                    time_matrix[routes[d][-1]][depot_idx] if routes[d] else 0
                )

                added_time = (
                    travel_to + place.visit_duration_min
                    + travel_back - current_return
                )
                new_time = day_time[d] + added_time
                new_cost = day_cost[d] + place.cost

                if new_time <= cfg.t_max_per_day and new_cost <= cfg.b_max_per_day:
                    routes[d].append(place.index)
                    day_time[d] = new_time
                    day_cost[d] = new_cost
                    inserted = True
                    break

            if not inserted:
                unvisited.append(place.index)

        return OPSolution(routes=routes, unvisited=unvisited)

    # ─── Выбор оператора ──────────────────────────────────────────────

    def _apply_random_operator(
        self,
        solution: OPSolution,
        depot_idx: int,
        distance_matrix: List[List[float]],
        time_matrix: List[List[float]],
        place_by_idx: Dict[int, OPPlaceParams],
        cfg: OPConfig,
    ) -> Optional[OPSolution]:
        """
        Выбирает оператор соседства по распределению вероятностей
        (p₁, p₂, p₃, p₄, p₅) и применяет его к текущему решению.
        """
        r = random.random()
        cumulative = 0.0

        operators = [
            (cfg.prob_2opt,   self._op_2opt),
            (cfg.prob_insert, self._op_insert),
            (cfg.prob_remove, self._op_remove),
            (cfg.prob_swap,   self._op_swap),
            (cfg.prob_move,   self._op_move),
        ]

        for prob, op_func in operators:
            cumulative += prob
            if r < cumulative:
                return op_func(solution, depot_idx, time_matrix, place_by_idx, cfg)

        return self._op_2opt(solution, depot_idx, time_matrix, place_by_idx, cfg)

    def _copy_solution(self, solution: OPSolution) -> OPSolution:
        """Глубокая копия решения для генерации соседа."""
        return OPSolution(
            routes=[list(r) for r in solution.routes],
            unvisited=list(solution.unvisited),
        )

    # ─── Оператор 1: 2-opt ───────────────────────────────────────────

    def _op_2opt(self, solution, depot_idx, time_matrix, place_by_idx, cfg) -> Optional[OPSolution]:
        """
        Оператор 2-opt: реверс подсегмента [i, j] внутри маршрута
        случайного дня. Улучшает порядок обхода без изменения набора мест.

        R_d = [… a, b, c, d, e …]  →  R_d' = [… a, d, c, b, e …]
        """
        non_empty = [d for d, r in enumerate(solution.routes) if len(r) >= 2]
        if not non_empty:
            return None

        d = random.choice(non_empty)
        route = solution.routes[d]
        n = len(route)
        i = random.randint(0, n - 2)
        j = random.randint(i + 1, n - 1)

        new_sol = self._copy_solution(solution)
        new_sol.routes[d][i:j + 1] = reversed(new_sol.routes[d][i:j + 1])
        return new_sol

    # ─── Оператор 2: Insert ──────────────────────────────────────────

    def _op_insert(self, solution, depot_idx, time_matrix, place_by_idx, cfg) -> Optional[OPSolution]:
        """
        Оператор Insert: вставляет случайный непосещённый объект
        в случайную позицию случайного дня.

        Unvisited: {p} → ∅,   R_d: [… a, b …] → [… a, p, b …]
        """
        if not solution.unvisited:
            return None

        new_sol = self._copy_solution(solution)
        place_idx = random.choice(new_sol.unvisited)
        d = random.randint(0, len(new_sol.routes) - 1)
        pos = random.randint(0, len(new_sol.routes[d]))

        new_sol.routes[d].insert(pos, place_idx)
        new_sol.unvisited.remove(place_idx)
        return new_sol

    # ─── Оператор 3: Remove ──────────────────────────────────────────

    def _op_remove(self, solution, depot_idx, time_matrix, place_by_idx, cfg) -> Optional[OPSolution]:
        """
        Оператор Remove: удаляет случайный объект из случайного дня,
        возвращая его в множество непосещённых.

        R_d: [… a, p, b …] → [… a, b …],   Unvisited: ∅ → {p}
        """
        non_empty = [d for d, r in enumerate(solution.routes) if r]
        if not non_empty:
            return None

        new_sol = self._copy_solution(solution)
        d = random.choice(non_empty)
        pos = random.randint(0, len(new_sol.routes[d]) - 1)
        removed = new_sol.routes[d].pop(pos)
        new_sol.unvisited.append(removed)
        return new_sol

    # ─── Оператор 4: Swap ────────────────────────────────────────────

    def _op_swap(self, solution, depot_idx, time_matrix, place_by_idx, cfg) -> Optional[OPSolution]:
        """
        Оператор Swap: обменивает посещённый объект p_v с непосещённым p_u.

        R_d: [… p_v …] → [… p_u …],   Unvisited: {p_u} → {p_v}
        """
        non_empty = [d for d, r in enumerate(solution.routes) if r]
        if not non_empty or not solution.unvisited:
            return None

        new_sol = self._copy_solution(solution)
        d = random.choice(non_empty)
        pos = random.randint(0, len(new_sol.routes[d]) - 1)
        ui = random.randint(0, len(new_sol.unvisited) - 1)

        old_place = new_sol.routes[d][pos]
        new_place = new_sol.unvisited[ui]

        new_sol.routes[d][pos] = new_place
        new_sol.unvisited[ui] = old_place
        return new_sol

    # ─── Оператор 5: Move ────────────────────────────────────────────

    def _op_move(self, solution, depot_idx, time_matrix, place_by_idx, cfg) -> Optional[OPSolution]:
        """
        Оператор Move: перемещает объект из одного дня в другой.

        R_src: [… p …] → [… …],   R_dst: [… a, b …] → [… a, p, b …]
        """
        if len(solution.routes) < 2:
            return None

        non_empty = [d for d, r in enumerate(solution.routes) if r]
        if not non_empty:
            return None

        new_sol = self._copy_solution(solution)
        src = random.choice(non_empty)
        dst = random.choice([d for d in range(len(new_sol.routes)) if d != src])

        pos_src = random.randint(0, len(new_sol.routes[src]) - 1)
        place_idx = new_sol.routes[src].pop(pos_src)

        pos_dst = random.randint(0, len(new_sol.routes[dst]))
        new_sol.routes[dst].insert(pos_dst, place_idx)
        return new_sol

    # ─── Целевая функция ──────────────────────────────────────────────

    def _day_objective(
        self,
        route: List[int],
        depot_idx: int,
        distance_matrix: List[List[float]],
        time_matrix: List[List[float]],
        place_by_idx: Dict[int, OPPlaceParams],
        cfg: OPConfig,
    ) -> float:
        """
        Целевая функция одного дня:
            F(R_d) = λ₁·Q(R_d) − λ₂·D̃(R_d) − λ₃·T̃(R_d) − λ₄·C̃(R_d) − penalty

        Нормализация для сопоставимости масштабов:
            D̃ = D / d_max,  T̃ = T / T_ref,  C̃ = C / C_ref

        Маршрут дня: depot → p₁ → p₂ → … → p_n → depot

        Штрафы за нарушение ограничений:
            penalty = w · max(0, T̃ − 1) + w · max(0, C̃ − C_lim/C_ref)
        """
        if not route:
            return 0.0

        # Q(R_d) = Σ_{i ∈ R_d} q_i  (q_i ∈ [0, 1] после нормализации рейтинга)
        q_r = sum(place_by_idx[i].quality for i in route if i in place_by_idx)

        # Полный путь дня: depot → p₁ → … → p_n → depot
        full_path = [depot_idx] + route + [depot_idx]
        m = len(full_path)

        # D(R_d) = Σ d(p_k, p_{k+1})
        d_r = sum(
            distance_matrix[full_path[k]][full_path[k + 1]]
            for k in range(m - 1)
        )

        # T(R_d) = Σ t(p_k, p_{k+1}) + Σ v_i
        travel_time = sum(
            time_matrix[full_path[k]][full_path[k + 1]]
            for k in range(m - 1)
        )
        visit_time = sum(
            place_by_idx[i].visit_duration_min
            for i in route if i in place_by_idx
        )
        t_r = travel_time + visit_time

        # C(R_d) = Σ_{i ∈ R_d} c_i
        c_r = sum(place_by_idx[i].cost for i in route if i in place_by_idx)

        # Нормализация: D̃ = D/d_ref, T̃ = T/T_ref, C̃ = C/C_ref
        d_norm = d_r / self._d_ref
        t_norm = t_r / self._t_ref
        c_norm = c_r / self._c_ref

        # F(R_d) = λ₁·Q − λ₂·D̃ − λ₃·T̃ − λ₄·C̃
        f = (
            cfg.lambda_quality * q_r
            - cfg.lambda_distance * d_norm
            - cfg.lambda_time * t_norm
            - cfg.lambda_cost * c_norm
        )

        # Штрафы за нарушение ограничений (в нормализованном масштабе)
        if t_r > cfg.t_max_per_day:
            f -= cfg.penalty_weight * ((t_r - cfg.t_max_per_day) / self._t_ref)
        if c_r > cfg.b_max_per_day:
            f -= cfg.penalty_weight * ((c_r - cfg.b_max_per_day) / self._c_ref)

        return f

    def _total_objective(
        self,
        solution: OPSolution,
        depot_idx: int,
        distance_matrix: List[List[float]],
        time_matrix: List[List[float]],
        place_by_idx: Dict[int, OPPlaceParams],
        cfg: OPConfig,
    ) -> float:
        """
        Суммарная целевая функция:
            F(R) = Σ_{d=1}^{D} F(R_d)
        """
        base = sum(
            self._day_objective(
                route, depot_idx, distance_matrix, time_matrix,
                place_by_idx, cfg,
            )
            for route in solution.routes
        )
        # Штраф за отклонение длины маршрута от желаемой (task #3).
        if cfg.desired_places_per_day and cfg.desired_places_per_day > 0:
            target = cfg.desired_places_per_day
            penalty = 0.0
            for route in solution.routes:
                diff = target - len(route)
                if diff > 0:
                    # Не добирает до цели — штраф квадратичный.
                    penalty += cfg.desired_places_penalty * (diff ** 2)
                elif diff < 0:
                    # Превышение штрафуется слабее (в 2 раза).
                    penalty += 0.5 * cfg.desired_places_penalty * (abs(diff) ** 2)
            base -= penalty
        return base
