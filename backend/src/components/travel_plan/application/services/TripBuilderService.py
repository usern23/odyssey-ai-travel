"""TripBuilderService — manual editing operations on an existing TravelPlan.

Distinct from :class:`TravelPlanService.generate_plan` which builds a fresh
plan with the orienteering solver.  The builder accepts pure user intent
(add/remove/reorder/move/promote-from-wishlist) and re-derives the day
schedule (travel times, distances, opening-hours-adjusted starts) using the
same primitives that the agent uses, so that the resulting plan is fully
compatible with downstream consumers (Markdown/render, replan, agent).

All mutating methods return the *same* TravelPlan instance for chaining.
Persistence and version-conflict handling live in the web layer.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from src.components.travel_plan.domain.TravelPlanEntities import (
    Activity,
    DAY_WINDOW_END,
    DAY_WINDOW_START,
    DayPlan,
    Place,
    PlaceCategory,
    TIME_ROUND_MINUTES,
    TravelPlan,
)
from src.components.travel_plan.application.services.TravelPlanService import (
    TravelPlanService,
)
from src.components.travel_plan.infrastructure.clients.OrsClient import ORSClient

logger = logging.getLogger(__name__)


class VersionConflictError(Exception):
    """Raised when a manual edit is rejected because the plan was changed
    elsewhere (optimistic locking)."""

    def __init__(self, expected: int, actual: int):
        super().__init__(
            f'Plan version conflict: expected {expected}, got {actual}',
        )
        self.expected = expected
        self.actual = actual


class PlaceDoesNotFitError(Exception):
    """Raised by add_place_to_day when the new place cannot be scheduled
    inside the day window or venue opening hours."""

    def __init__(
        self,
        place_name: str,
        reason: str,
        end_hour: int,
    ):
        self.place_name = place_name
        self.reason = reason
        self.end_hour = end_hour
        super().__init__(
            f'Place {place_name!r} does not fit ({reason}, day ends at {end_hour}:00)'
        )


class TripBuilderService:
    """Apply granular manual edits to a TravelPlan and recompute metrics."""

    def __init__(self, ors_client: Optional[ORSClient] = None):
        self.ors_client = ors_client or ORSClient()
        # Reuse TravelPlanService for matrix + schedule helpers.
        self._planner = TravelPlanService(self.ors_client)
        # Populated by ``recompute_day`` after each call: places that the
        # schedule builder dropped because they overflow the day window or
        # venue opening hours. Callers (e.g. ``add_place_to_day``) inspect
        # this to surface the issue to the user instead of silently losing
        # the place.
        self.last_skipped: List[Place] = []

    # ── Version handling ─────────────────────────────────────────────
    @staticmethod
    def check_version(plan: TravelPlan, expected: Optional[int]) -> None:
        """Raise ``VersionConflictError`` when client's expected version
        does not match the plan. ``None`` skips the check (legacy clients).
        """
        if expected is None:
            return
        actual = int(getattr(plan, 'version', 1) or 1)
        if int(expected) != actual:
            raise VersionConflictError(expected=int(expected), actual=actual)

    @staticmethod
    def bump_version(plan: TravelPlan, mark_mixed: bool = True) -> None:
        """Increment plan.version after a successful mutation.  When
        ``mark_mixed`` is True and the plan was originally agent-generated,
        mark it as 'mixed' so the UI can show that origin.
        """
        plan.version = int(getattr(plan, 'version', 1) or 1) + 1
        if mark_mixed and plan.source == 'agent':
            plan.source = 'mixed'

    # ── Day-level recompute ─────────────────────────────────────────
    async def recompute_day(self, plan: TravelPlan, day_number: int) -> DayPlan:
        """Rebuild start/end times, travel times and distances for a single
        day given the *current* order of activities.

        Implementation: take ``day.activities[*].place`` in their current
        order, fetch an ORS matrix for hotel + all places of this day, then
        run the same schedule builder used by ``generate_plan``.  Skipped
        places (window/hours overflow) are preserved as activities with
        their original times — the caller decides whether to drop them.
        """
        day = plan.get_day(day_number)
        if day is None:
            raise ValueError(f'Day {day_number} not found in plan')

        if not day.activities:
            day.total_distance_km = 0.0
            day.total_travel_time_min = 0
            day.total_visit_time_min = 0
            plan._recalculate_stats()
            return day

        hotel = plan.hotel
        day_places: List[Place] = [a.place for a in day.activities]
        all_points = [(hotel.lat, hotel.lon)] + [
            (p.lat, p.lon) for p in day_places
        ]
        try:
            distance_matrix = await self._planner._get_ors_matrix(all_points)
        except Exception as e:
            logger.warning(f'recompute_day: ORS matrix failed, falling back: {e}')
            from src.components.travel_plan.application.solvers.TspSolver import (
                build_distance_matrix_haversine,
            )
            distance_matrix = build_distance_matrix_haversine(all_points)

        # Day starts at the user-configured start_hour (mirrors generate_plan).
        try:
            start_t = time(int(plan.start_hour or 10), 0)
        except Exception:
            start_t = DAY_WINDOW_START
        # End-of-day cap (defaults to 22:00 if plan has no override).
        try:
            end_h = int(getattr(plan, 'end_hour', 22) or 22)
            if end_h >= 24:
                end_t = time(23, 59)
            else:
                end_t = time(min(end_h, 23), 0)
        except Exception:
            end_t = DAY_WINDOW_END

        rebuilt_days, _skipped = self._planner._build_schedule(
            optimized_days=[day_places],
            start_date=day.date,
            start_time=start_t,
            distance_matrix=distance_matrix,
            all_points=all_points,
            hotel=hotel,
            return_skipped=True,
            end_time=end_t,
        )
        # Expose for upstream handlers (add_place_to_day raises 409 when
        # the just-added place ends up here). _build_schedule numbers the
        # passed-in days starting from 1, so the single day we feed it is
        # always at key 1.
        if isinstance(_skipped, dict):
            self.last_skipped = list(_skipped.get(1, []))
        else:
            self.last_skipped = list(_skipped or [])
        rebuilt = rebuilt_days[0]
        rebuilt.day_number = day_number
        rebuilt.heading = day.heading
        # Preserve user-authored activity-level fields (note/cost/lock)
        # by mapping them back from the original list-by-place-key.
        old_by_key: Dict[Tuple[str, float, float], Activity] = {
            (a.place.name.lower(), round(a.place.lat, 5), round(a.place.lon, 5)): a
            for a in day.activities
        }
        for new_act in rebuilt.activities:
            key = (
                new_act.place.name.lower(),
                round(new_act.place.lat, 5),
                round(new_act.place.lon, 5),
            )
            old = old_by_key.get(key)
            if old is not None:
                new_act.note = old.note
                new_act.actual_cost = old.actual_cost
                new_act.is_locked = old.is_locked
                new_act.notes = old.notes

        # Replace day in plan in-place.
        for i, d in enumerate(plan.days):
            if d.day_number == day_number:
                plan.days[i] = rebuilt
                break

        # Fetch real ORS route geometry so the map shows the road path
        # instead of straight place-to-place lines. Failures are logged
        # by ``_add_route_geometry`` and leave ``route_geometry=None``,
        # which the frontend handles by falling back to straight lines.
        try:
            await self._planner._add_route_geometry([rebuilt], hotel)
        except Exception as e:
            logger.warning(
                f'recompute_day: route geometry failed for day {day_number}: {e}')

        plan._recalculate_stats()
        return rebuilt

    # ── Day CRUD ────────────────────────────────────────────────────
    async def add_place_to_day(
        self,
        plan: TravelPlan,
        day_number: int,
        place: Place,
        index: Optional[int] = None,
        is_locked: bool = False,
        note: Optional[str] = None,
        actual_cost: Optional[float] = None,
    ) -> DayPlan:
        day = plan.get_day(day_number)
        if day is None:
            raise ValueError(f'Day {day_number} not found in plan')
        # Provisional Activity — start/end will be overwritten by recompute.
        activity = Activity(
            place=place,
            start_time=time(0, 0),
            end_time=time(0, 0),
            note=note,
            actual_cost=actual_cost,
            is_locked=is_locked,
        )
        if index is None or index < 0 or index >= len(day.activities):
            day.activities.append(activity)
        else:
            day.activities.insert(int(index), activity)

        # Snapshot pre-recompute so we can restore if the new place gets
        # skipped (window overflow / venue closed) and the caller wants
        # hard-mode rejection.
        prev_activities_snapshot = [a for a in day.activities if a is not activity]

        rebuilt = await self.recompute_day(plan, day_number)

        # Hard mode: refuse to silently lose the place.
        def _key(p: Place) -> tuple:
            return (p.name.strip().lower(), round(p.lat, 5), round(p.lon, 5))

        added_key = _key(place)
        if any(_key(p) == added_key for p in self.last_skipped):
            # Restore previous activities and recompute back to the
            # pre-insert state so the in-memory plan stays consistent.
            day_after = plan.get_day(day_number)
            if day_after is not None:
                day_after.activities = prev_activities_snapshot
                try:
                    await self.recompute_day(plan, day_number)
                except Exception:
                    pass
            try:
                end_h = int(getattr(plan, 'end_hour', 22) or 22)
            except Exception:
                end_h = 22
            reason = 'out_of_day_window'
            try:
                from src.components.travel_plan.domain.TravelPlanEntities import (
                    resolve_opening_window,
                )
                open_t, close_t = resolve_opening_window(
                    place.opening_hours, place.category.value,
                    day_start=time(min(int(plan.start_hour or 10), 23), 0),
                    day_end=time(min(end_h, 23), 0) if end_h < 24 else time(23, 59),
                )
                if close_t.hour < end_h:
                    reason = 'venue_closed'
            except Exception:
                pass
            raise PlaceDoesNotFitError(
                place_name=place.name, reason=reason, end_hour=end_h,
            )

        return rebuilt

    async def remove_place_from_day(
        self, plan: TravelPlan, day_number: int, activity_index: int,
    ) -> DayPlan:
        day = plan.get_day(day_number)
        if day is None:
            raise ValueError(f'Day {day_number} not found in plan')
        if activity_index < 0 or activity_index >= len(day.activities):
            raise ValueError(
                f'Activity index {activity_index} out of range '
                f'for day {day_number}',
            )
        day.activities.pop(activity_index)
        return await self.recompute_day(plan, day_number)

    async def update_activity(
        self,
        plan: TravelPlan,
        day_number: int,
        activity_index: int,
        note: Optional[str] = None,
        actual_cost: Optional[float] = None,
        is_locked: Optional[bool] = None,
        visit_duration_min: Optional[int] = None,
    ) -> DayPlan:
        day = plan.get_day(day_number)
        if day is None:
            raise ValueError(f'Day {day_number} not found in plan')
        if activity_index < 0 or activity_index >= len(day.activities):
            raise ValueError(
                f'Activity index {activity_index} out of range',
            )
        act = day.activities[activity_index]
        if note is not None:
            act.note = note or None
        if actual_cost is not None:
            act.actual_cost = float(actual_cost) if actual_cost >= 0 else None
        if is_locked is not None:
            act.is_locked = bool(is_locked)
        if visit_duration_min is not None and visit_duration_min > 0:
            act.place.visit_duration_min = int(visit_duration_min)
            return await self.recompute_day(plan, day_number)
        return day  # no schedule change

    async def reorder_day(
        self, plan: TravelPlan, day_number: int, new_indices: List[int],
    ) -> DayPlan:
        day = plan.get_day(day_number)
        if day is None:
            raise ValueError(f'Day {day_number} not found in plan')
        if sorted(new_indices) != list(range(len(day.activities))):
            raise ValueError(
                'reorder_day: new_indices must be a permutation '
                f'of 0..{len(day.activities) - 1}',
            )
        day.activities = [day.activities[i] for i in new_indices]
        return await self.recompute_day(plan, day_number)

    async def move_place(
        self,
        plan: TravelPlan,
        from_day: int,
        to_day: int,
        activity_index: int,
        target_index: Optional[int] = None,
    ) -> Tuple[DayPlan, DayPlan]:
        if from_day == to_day:
            # Treat as a reorder within the day.
            day = plan.get_day(from_day)
            if day is None:
                raise ValueError(f'Day {from_day} not found in plan')
            if activity_index < 0 or activity_index >= len(day.activities):
                raise ValueError('activity_index out of range')
            act = day.activities.pop(activity_index)
            ti = (
                target_index
                if target_index is not None and 0 <= target_index <= len(day.activities)
                else len(day.activities)
            )
            day.activities.insert(int(ti), act)
            new_day = await self.recompute_day(plan, from_day)
            return new_day, new_day
        src = plan.get_day(from_day)
        dst = plan.get_day(to_day)
        if src is None or dst is None:
            raise ValueError('from_day/to_day not found in plan')
        if activity_index < 0 or activity_index >= len(src.activities):
            raise ValueError('activity_index out of range')
        act = src.activities.pop(activity_index)
        ti = (
            target_index
            if target_index is not None and 0 <= target_index <= len(dst.activities)
            else len(dst.activities)
        )
        dst.activities.insert(int(ti), act)
        new_src = await self.recompute_day(plan, from_day)
        new_dst = await self.recompute_day(plan, to_day)
        return new_src, new_dst

    # ── Wishlist ────────────────────────────────────────────────────
    def add_to_wishlist(self, plan: TravelPlan, place: Place) -> None:
        # De-duplicate by (name, lat, lon) — typical case is the user
        # clicking "save" on the same card twice.
        key = (place.name.lower(), round(place.lat, 5), round(place.lon, 5))
        for existing in plan.wishlist:
            ek = (
                existing.name.lower(),
                round(existing.lat, 5),
                round(existing.lon, 5),
            )
            if ek == key:
                return
        plan.wishlist.append(place)

    def remove_from_wishlist(self, plan: TravelPlan, index: int) -> None:
        if index < 0 or index >= len(plan.wishlist):
            raise ValueError(f'Wishlist index {index} out of range')
        plan.wishlist.pop(index)

    async def promote_from_wishlist(
        self,
        plan: TravelPlan,
        wishlist_index: int,
        day_number: int,
        target_index: Optional[int] = None,
    ) -> DayPlan:
        if wishlist_index < 0 or wishlist_index >= len(plan.wishlist):
            raise ValueError(f'Wishlist index {wishlist_index} out of range')
        place = plan.wishlist.pop(wishlist_index)
        return await self.add_place_to_day(
            plan, day_number, place, index=target_index,
        )

    # ── Budget ──────────────────────────────────────────────────────
    def update_budget(
        self,
        plan: TravelPlan,
        total: Optional[float] = None,
        by_category: Optional[Dict[str, float]] = None,
        currency: Optional[str] = None,
        lodging_total: Optional[float] = None,
        transport_total: Optional[float] = None,
    ) -> None:
        if total is not None:
            plan.budget_total = float(total) if total >= 0 else None
        if by_category is not None:
            plan.budget_by_category = {
                str(k): float(v) for k, v in by_category.items() if v is not None
            }
        if currency:
            plan.budget_currency = str(currency).upper()[:8]
        if lodging_total is not None:
            plan.lodging_total = float(lodging_total) if lodging_total >= 0 else None
        if transport_total is not None:
            plan.transport_total = float(transport_total) if transport_total >= 0 else None

    # ── Hotel ───────────────────────────────────────────────────────
    async def update_hotel(
        self,
        plan: TravelPlan,
        new_hotel: Optional[Place],
    ) -> None:
        """Replace the trip's hotel/starting point.

        - ``new_hotel=None`` keeps existing if any (caller is expected
          to pre-resolve the fallback "centre of destination" place).
        - When the hotel actually changes, all day matrices are
          implicitly invalidated; ``recompute_day`` is called for every
          day to refresh travel times from the new origin.
        """
        if new_hotel is None:
            return
        # Skip if identical (avoid version churn).
        old = plan.hotel
        if (
            old
            and old.name == new_hotel.name
            and abs(old.lat - new_hotel.lat) < 1e-6
            and abs(old.lon - new_hotel.lon) < 1e-6
        ):
            return
        plan.hotel = new_hotel
        for day in plan.days:
            await self.recompute_day(plan, day.day_number)

    # ── Optimisation (TOP-solver respecting locks) ──────────────────
    async def optimize_day(self, plan: TravelPlan, day_number: int) -> DayPlan:
        """Re-run the orienteering solver on a single day, respecting locks.

        Locked activities stay at their relative positions; the solver only
        permutes/inserts free activities and fills the day from
        ``plan.candidates`` if there is room.
        """
        day = plan.get_day(day_number)
        if day is None:
            raise ValueError(f'Day {day_number} not found in plan')

        locked = [a for a in day.activities if a.is_locked]
        free_places = [a.place for a in day.activities if not a.is_locked]

        # Lightweight strategy for v1: keep locked activities at the start
        # (in their current order), then run the solver over the remaining
        # places only. We intentionally DO NOT mix in plan.candidates here:
        # those are the broader pool from the initial generation and they
        # tend to crowd out the user's curated places when the day's time
        # window is tight, which feels like "places disappear after
        # optimize". Candidates are only re-introduced explicitly via the
        # "Find more places" action.
        pool: List[Place] = list(free_places)
        used = {(p.name.lower(), round(p.lat, 5), round(p.lon, 5))
                for p in pool}
        used.update(
            (a.place.name.lower(), round(a.place.lat, 5), round(a.place.lon, 5))
            for a in locked
        )

        # Re-use the existing solver via TravelPlanService.replan_day
        # which already understands category modifiers, opening hours and
        # candidate-pool top-up.  We reset the day's activities to the
        # locked anchors first, then call replan_day to fill the rest.
        day.activities = list(locked)
        plan._recalculate_stats()
        from datetime import datetime as _dt
        # current_datetime = day start (= user's start_hour) so the solver
        # uses the full day window.
        try:
            start_h = int(plan.start_hour or 10)
        except Exception:
            start_h = 10
        current_dt = _dt.combine(day.date, time(start_h, 0))
        plan = await self._planner.replan_day(
            plan=plan,
            day_number=day_number,
            current_datetime=current_dt,
            visited_place_names=[],
            additional_candidates=pool or None,
        )
        return plan.get_day(day_number)
