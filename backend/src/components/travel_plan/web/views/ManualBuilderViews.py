"""All HTTP views for the manual trip builder.

Single-file convention: each endpoint is a thin class with a single
``__call__`` method.  Heavy lifting is delegated to
:class:`TripBuilderService`.

All mutating endpoints honour optimistic locking via
``expected_version`` (body) or ``expected_version`` (query) for DELETE.
"""
from __future__ import annotations

import logging
from datetime import date as _date, time as _time
from typing import Any, Dict, Optional

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.web.dependencies import get_current_user
from src.components.chats.application.core.commands.ICreateChatCommand import (
    ICreateChatCommand,
)
from src.components.chats.application.core.commands.ILinkTripToChatCommand import (
    ILinkTripToChatCommand,
)
from src.components.chats.infrastructure.models.ChatModel import Chat
from src.components.trips.application.core.commands import (
    ICreateTripCommand,
    IUpdateGeneratedPlanCommand,
)
from src.components.trips.application.core.queries import IGetTripQuery
from src.components.trips.web.models.TripResponse import TripResponse
from src.components.travel_plan.application.services.TripBuilderService import (
    PlaceDoesNotFitError,
    TripBuilderService,
    VersionConflictError,
)
from src.components.travel_plan.domain.TravelPlanEntities import (
    DayPlan,
    Place,
    PlaceCategory,
    TravelPlan,
)
from src.components.travel_plan.infrastructure.clients.OrsClient import (
    ORSClient,
    ORSError,
)
from src.components.travel_plan.web.models.ManualBuilderModels import (
    AddPlaceRequest,
    AskAiRequest,
    CreateManualTripRequest,
    MovePlaceRequest,
    OptimizeDayRequest,
    PlacePayload,
    PromoteWishlistRequest,
    ReorderDayRequest,
    SearchPlacesRequest,
    UpdateActivityRequest,
    UpdateBudgetRequest,
    UpdateHotelRequest,
    WishlistAddRequest,
)
from src.components.users.infrastructure.models import User

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────
def _place_from_payload(payload: PlacePayload) -> Place:
    try:
        cat = PlaceCategory(payload.category)
    except ValueError:
        cat = PlaceCategory.OTHER
    return Place(
        name=payload.name,
        lat=payload.lat,
        lon=payload.lon,
        category=cat,
        visit_duration_min=payload.visit_duration_min,
        opening_hours=payload.opening_hours,
        description=payload.description,
        address=payload.address,
        rating=payload.rating,
        price_level=payload.price_level,
        source=payload.source or 'manual',
    )


async def _load_trip_and_plan(
    get_trip: IGetTripQuery, user_id: int, trip_id: int,
) -> tuple[Any, Dict[str, Any], TravelPlan]:
    trip = await get_trip.execute(user_id, trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Trip not found',
        )
    stored = trip.generated_plan or {}
    if not isinstance(stored, dict):
        stored = {}
    plan_dict = stored.get('plan_data')
    if not plan_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Trip has no plan to edit. Generate or create a manual '
                   'trip first.',
        )
    try:
        plan = TravelPlan.from_dict(plan_dict)
    except Exception as e:
        logger.error(f'Failed to deserialize plan for trip {trip_id}: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Stored plan is corrupted.',
        )
    return trip, stored, plan


async def _persist_plan(
    update_plan: IUpdateGeneratedPlanCommand,
    trip_id: int,
    stored: Dict[str, Any],
    plan: TravelPlan,
    mark_mixed: bool = True,
) -> Any:
    TripBuilderService.bump_version(plan, mark_mixed=mark_mixed)
    new_stored = dict(stored)
    new_stored['plan_data'] = plan.to_dict()
    return await update_plan.execute(trip_id, new_stored)


def _check_version(plan: TravelPlan, expected: Optional[int]) -> None:
    try:
        TripBuilderService.check_version(plan, expected)
    except VersionConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                'error': 'version_conflict',
                'expected': e.expected,
                'actual': e.actual,
                'message': str(e),
            },
        )


def _bad(msg: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ════════════════════════════════════════════════════════════════════
# 1. CREATE MANUAL TRIP — POST /trips/manual
# ════════════════════════════════════════════════════════════════════
class CreateManualTripView:
    """Create an empty trip with a manually authored TravelPlan skeleton.

    Result: a Trip row with ``generated_plan = {plan_data: <empty plan>}``
    where the plan has the supplied hotel, date range and one DayPlan per
    date (no activities).  Subsequent edits go through the per-day
    endpoints.
    """

    @inject
    async def __call__(
        self,
        create_trip: FromDishka[ICreateTripCommand],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: CreateManualTripRequest = Body(...),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        if payload.start_date and payload.end_date:
            if payload.end_date < payload.start_date:
                raise _bad('end_date must be on or after start_date')
            duration_days = (payload.end_date - payload.start_date).days + 1
        else:
            duration_days = 1
        if duration_days <= 0 or duration_days > 60:
            raise _bad('duration_days must be 1..60')

        if payload.hotel is not None:
            hotel = _place_from_payload(payload.hotel)
        else:
            # No hotel supplied — geocode `destination` and use its
            # centre as a synthetic starting point. Falls back to (0,0)
            # only if geocoding fails so the user can still create a
            # trip and adjust later.
            lat, lon = 0.0, 0.0
            try:
                ors = ORSClient()
                result = await ors.geocode(payload.destination)
                if result is not None:
                    lat, lon = result
                await ors.close()
            except ORSError as e:
                logger.warning(
                    f"Could not geocode '{payload.destination}': {e}",
                )
            hotel = Place(
                name=f'Центр · {payload.destination}',
                lat=lat,
                lon=lon,
                category=PlaceCategory.OTHER,
                visit_duration_min=0,
                description='Стартовая точка по умолчанию (центр города). '
                'Замените на свой отель в редакторе.',
                source='auto',
            )
        # Build skeleton plan: one empty day per date.
        start_date = payload.start_date or _date.today()
        from datetime import timedelta
        days = []
        for i in range(duration_days):
            days.append(
                DayPlan(
                    day_number=i + 1,
                    date=start_date + timedelta(days=i),
                    activities=[],
                    total_distance_km=0.0,
                    total_travel_time_min=0,
                    total_visit_time_min=0,
                ),
            )

        plan = TravelPlan(
            destination=payload.destination or '',
            hotel=hotel,
            days=days,
            start_date=start_date,
            end_date=start_date + timedelta(days=duration_days - 1),
            candidates=[],
            start_hour=int(payload.start_hour or 10),
            end_hour=int(getattr(payload, 'end_hour', None) or 22),
        )
        plan.source = 'manual'
        plan.version = 1

        # First, create the Trip row (generated_plan empty), then update
        # with the plan dict — this avoids overloading the create command.
        trip = await create_trip.execute(
            user_id=current_user.id,
            name=payload.name,
            destination=payload.destination,
            origin=payload.origin,
            start_date=payload.start_date,
            end_date=payload.end_date,
            trip_profile=payload.trip_profile or {},
            generated_plan={},
        )
        trip = await update_plan.execute(
            trip.id, {'plan_data': plan.to_dict()},
        )
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 2. ADD PLACE TO DAY — POST /trips/{id}/days/{n}/places
# ════════════════════════════════════════════════════════════════════
class AddPlaceToDayView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        day_number: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: AddPlaceRequest = Body(...),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, payload.expected_version)
        place = _place_from_payload(payload.place)
        try:
            await TripBuilderService().add_place_to_day(
                plan, day_number, place,
                index=payload.index,
                is_locked=payload.is_locked,
                note=payload.note,
                actual_cost=payload.actual_cost,
            )
        except PlaceDoesNotFitError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    'code': 'PLACE_DOES_NOT_FIT',
                    'place_name': e.place_name,
                    'reason': e.reason,
                    'day_end_hour': e.end_hour,
                    'message': (
                        f'Место «{e.place_name}» не помещается в день '
                        f'(окно до {e.end_hour}:00). Продлите день или '
                        f'перенесите в другой день.'
                    ),
                },
            )
        except ValueError as e:
            raise _bad(str(e))
        trip = await _persist_plan(update_plan, trip_id, stored, plan)
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 3. UPDATE ACTIVITY — PATCH /trips/{id}/days/{n}/places/{idx}
# ════════════════════════════════════════════════════════════════════
class UpdateActivityView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        day_number: int,
        activity_index: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: UpdateActivityRequest = Body(...),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, payload.expected_version)
        try:
            await TripBuilderService().update_activity(
                plan, day_number, activity_index,
                note=payload.note,
                actual_cost=payload.actual_cost,
                is_locked=payload.is_locked,
                visit_duration_min=payload.visit_duration_min,
            )
        except ValueError as e:
            raise _bad(str(e))
        trip = await _persist_plan(update_plan, trip_id, stored, plan)
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 4. REMOVE PLACE — DELETE /trips/{id}/days/{n}/places/{idx}
# ════════════════════════════════════════════════════════════════════
class RemovePlaceFromDayView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        day_number: int,
        activity_index: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        expected_version: Optional[int] = Query(default=None),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, expected_version)
        try:
            await TripBuilderService().remove_place_from_day(
                plan, day_number, activity_index,
            )
        except ValueError as e:
            raise _bad(str(e))
        trip = await _persist_plan(update_plan, trip_id, stored, plan)
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 5. REORDER DAY — POST /trips/{id}/days/{n}/reorder
# ════════════════════════════════════════════════════════════════════
class ReorderDayView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        day_number: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: ReorderDayRequest = Body(...),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, payload.expected_version)
        try:
            await TripBuilderService().reorder_day(
                plan, day_number, payload.new_indices,
            )
        except ValueError as e:
            raise _bad(str(e))
        trip = await _persist_plan(update_plan, trip_id, stored, plan)
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 6. MOVE PLACE BETWEEN DAYS — POST /trips/{id}/places/move
# ════════════════════════════════════════════════════════════════════
class MovePlaceView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: MovePlaceRequest = Body(...),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, payload.expected_version)
        try:
            await TripBuilderService().move_place(
                plan,
                from_day=payload.from_day,
                to_day=payload.to_day,
                activity_index=payload.activity_index,
                target_index=payload.target_index,
            )
        except ValueError as e:
            raise _bad(str(e))
        trip = await _persist_plan(update_plan, trip_id, stored, plan)
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 7. ADD TO WISHLIST — POST /trips/{id}/wishlist
# ════════════════════════════════════════════════════════════════════
class AddToWishlistView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: WishlistAddRequest = Body(...),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, payload.expected_version)
        TripBuilderService().add_to_wishlist(
            plan, _place_from_payload(payload.place),
        )
        trip = await _persist_plan(update_plan, trip_id, stored, plan)
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 8. REMOVE FROM WISHLIST — DELETE /trips/{id}/wishlist/{idx}
# ════════════════════════════════════════════════════════════════════
class RemoveFromWishlistView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        wishlist_index: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        expected_version: Optional[int] = Query(default=None),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, expected_version)
        try:
            TripBuilderService().remove_from_wishlist(plan, wishlist_index)
        except ValueError as e:
            raise _bad(str(e))
        trip = await _persist_plan(update_plan, trip_id, stored, plan)
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 9. PROMOTE FROM WISHLIST — POST /trips/{id}/wishlist/{idx}/promote
# ════════════════════════════════════════════════════════════════════
class PromoteFromWishlistView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        wishlist_index: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: PromoteWishlistRequest = Body(...),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, payload.expected_version)
        try:
            await TripBuilderService().promote_from_wishlist(
                plan,
                wishlist_index=wishlist_index,
                day_number=payload.day_number,
                target_index=payload.target_index,
            )
        except ValueError as e:
            raise _bad(str(e))
        trip = await _persist_plan(update_plan, trip_id, stored, plan)
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 10. UPDATE BUDGET — PATCH /trips/{id}/budget
# ════════════════════════════════════════════════════════════════════
class UpdateBudgetView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: UpdateBudgetRequest = Body(...),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, payload.expected_version)
        TripBuilderService().update_budget(
            plan,
            total=payload.total,
            by_category=payload.by_category,
            currency=payload.currency,
            lodging_total=payload.lodging_total,
            transport_total=payload.transport_total,
        )
        trip = await _persist_plan(
            update_plan, trip_id, stored, plan, mark_mixed=False,
        )
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 10b. UPDATE HOTEL — PATCH /trips/{id}/hotel
# ════════════════════════════════════════════════════════════════════
class UpdateHotelView:
    """Replace or clear the trip's hotel/starting point.

    - When ``hotel`` is provided, it becomes the new starting point.
    - When ``hotel`` is null, server geocodes ``trip.destination`` and
      uses its centre as a placeholder (mirrors manual-create flow).
    """

    @inject
    async def __call__(
        self,
        trip_id: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: UpdateHotelRequest = Body(...),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, payload.expected_version)

        if payload.hotel is not None:
            new_hotel = _place_from_payload(payload.hotel)
        else:
            destination = plan.destination or ''
            lat, lon = 0.0, 0.0
            try:
                ors = ORSClient()
                result = await ors.geocode(destination) if destination else None
                if result is not None:
                    lat, lon = result
                await ors.close()
            except ORSError as e:
                logger.warning(
                    f"Could not geocode '{destination}': {e}",
                )
            new_hotel = Place(
                name=(
                    f'Центр · {destination}' if destination
                    else 'Центр'
                ),
                lat=lat,
                lon=lon,
                category=PlaceCategory.OTHER,
                visit_duration_min=0,
                description='Стартовая точка по умолчанию (центр города). '
                'Замените на свой отель в редакторе.',
                source='auto',
            )

        try:
            await TripBuilderService().update_hotel(plan, new_hotel)
        except ValueError as e:
            raise _bad(str(e))
        except Exception as e:
            logger.error(
                f'update_hotel failed for trip {trip_id}: {e}',
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f'Failed to update hotel: {e}',
            )
        trip = await _persist_plan(update_plan, trip_id, stored, plan)
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 11. OPTIMIZE DAY — POST /trips/{id}/days/{n}/optimize
# ════════════════════════════════════════════════════════════════════
class OptimizeDayPreviewView:
    """Run ``optimize_day`` on an in-memory copy of the plan and return a
    diff (added/removed/kept) without persisting. Lets the UI show a
    confirm dialog before applying.
    """

    @inject
    async def __call__(
        self,
        trip_id: int,
        day_number: int,
        get_trip: FromDishka[IGetTripQuery],
        payload: OptimizeDayRequest = Body(default=OptimizeDayRequest()),
        current_user: User = Depends(get_current_user),
    ) -> Dict[str, Any]:
        trip, _stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, payload.expected_version)
        # Deep copy via to_dict / from_dict round-trip.
        plan_copy = TravelPlan.from_dict(plan.to_dict())

        def _key(p: Place) -> tuple:
            return (p.name.strip().lower(), round(p.lat, 5), round(p.lon, 5))

        before_day = plan.get_day(day_number)
        if before_day is None:
            raise _bad(f'Day {day_number} not found in plan')
        before_keys = {_key(a.place): a.place.name for a in before_day.activities}
        try:
            await TripBuilderService().optimize_day(plan_copy, day_number)
        except ValueError as e:
            raise _bad(str(e))
        except Exception as e:
            logger.error(
                f'optimize_day preview failed for trip {trip_id} day {day_number}: {e}',
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f'Optimization failed: {e}',
            )
        after_day = plan_copy.get_day(day_number)
        after_keys = {_key(a.place): a.place.name for a in after_day.activities}
        added = [name for k, name in after_keys.items() if k not in before_keys]
        removed = [name for k, name in before_keys.items() if k not in after_keys]
        kept = [name for k, name in after_keys.items() if k in before_keys]
        return {
            'before_count': len(before_keys),
            'after_count': len(after_keys),
            'added': added,
            'removed': removed,
            'kept': kept,
            'total_distance_km_before': before_day.total_distance_km,
            'total_distance_km_after': after_day.total_distance_km,
            'total_travel_time_min_before': before_day.total_travel_time_min,
            'total_travel_time_min_after': after_day.total_travel_time_min,
        }


class OptimizeDayView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        day_number: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: OptimizeDayRequest = Body(default=OptimizeDayRequest()),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip, stored, plan = await _load_trip_and_plan(
            get_trip, current_user.id, trip_id,
        )
        _check_version(plan, payload.expected_version)
        try:
            await TripBuilderService().optimize_day(plan, day_number)
        except ValueError as e:
            raise _bad(str(e))
        except Exception as e:
            logger.error(
                f'optimize_day failed for trip {trip_id} day {day_number}: {e}',
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f'Optimization failed: {e}',
            )
        trip = await _persist_plan(update_plan, trip_id, stored, plan)
        return TripResponse.model_validate(trip, from_attributes=True)


# ════════════════════════════════════════════════════════════════════
# 12. SEARCH PLACES — POST /places/search
# ════════════════════════════════════════════════════════════════════
class SearchPlacesView:
    """Free-text place search via ORS Pelias.

    Front-end uses this for the «Add place» autocomplete: user types
    a few characters, we return up to ``limit`` ranked results with
    coordinates so that no manual lat/lon entry is needed.
    """

    @inject
    async def __call__(
        self,
        payload: SearchPlacesRequest = Body(...),
        current_user: User = Depends(get_current_user),
    ) -> Dict[str, Any]:
        if not payload.query or not payload.query.strip():
            raise _bad('query is required')
        ors = ORSClient()
        try:
            raw = await ors.search_places(
                payload.query.strip(),
                focus_lat=payload.near_lat,
                focus_lon=payload.near_lon,
                limit=payload.limit,
                radius_km=payload.radius_km,
            )
        except ORSError as e:
            logger.warning(f'Place search failed: {e}')
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={'error': 'geocoder_unavailable', 'message': str(e)},
            )
        finally:
            await ors.close()
        # Map Pelias layers to our PlaceCategory string. Pelias is not
        # POI-rich; most results land in the 'other' bucket but the lat/
        # lon is always usable.
        def map_category(layer: Optional[str]) -> str:
            if not layer:
                return 'other'
            l = layer.lower()
            if l in ('venue',):
                return 'landmark'
            if l in ('address', 'street'):
                return 'other'
            if l in ('locality', 'localadmin', 'region', 'country'):
                return 'other'
            return 'other'
        items = [
            {
                'name': r['name'],
                'lat': r['lat'],
                'lon': r['lon'],
                'category': map_category(r.get('layer')),
                'address': r.get('address'),
                'source': 'ors',
            }
            for r in raw
        ]
        return {'results': items, 'count': len(items)}


# ════════════════════════════════════════════════════════════════════
# 13. ASK AI ABOUT THIS TRIP — POST /trips/{id}/ask-ai
# ════════════════════════════════════════════════════════════════════
class AskAiForTripView:
    """Returns the chat that the user should stream messages to.

    Strategy: reuse ``trip.chats[0]`` if it exists, otherwise create a
    new chat and link it to the trip.  The frontend then issues regular
    requests to ``POST /chats/{chat_id}/messages``.
    """

    @inject
    async def __call__(
        self,
        trip_id: int,
        db_session: FromDishka[AsyncSession],
        get_trip: FromDishka[IGetTripQuery],
        create_chat: FromDishka[ICreateChatCommand],
        link_trip_to_chat: FromDishka[ILinkTripToChatCommand],
        payload: AskAiRequest = Body(default=AskAiRequest()),
        current_user: User = Depends(get_current_user),
    ) -> Dict[str, Any]:
        trip = await get_trip.execute(current_user.id, trip_id)
        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail='Trip not found',
            )
        # Find the most-recent chat already linked to this trip.
        result = await db_session.execute(
            select(Chat)
            .where(Chat.trip_id == trip_id, Chat.user_id == current_user.id)
            .order_by(Chat.id.desc())
            .limit(1),
        )
        chat = result.scalar_one_or_none()
        if chat is None:
            chat = await create_chat(user_id=current_user.id)
            await link_trip_to_chat(chat_id=chat.id, trip_id=trip_id)
            await db_session.commit()
            created = True
        else:
            created = False
        return {
            'chat_id': chat.id,
            'trip_id': trip_id,
            'created': created,
            'initial_message': payload.initial_message,
        }
