from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import Body, Depends, HTTPException, status

from src.common.web.dependencies import get_current_user
from src.components.trips.application.core.commands import IUpdateGeneratedPlanCommand
from src.components.trips.application.core.queries import IGetTripQuery
from src.components.trips.web.models.ReplanDayRequest import ReplanDayRequest
from src.components.trips.web.models.TripResponse import TripResponse
from src.components.users.infrastructure.models import User
from src.components.travel_plan.application.services.TravelPlanService import TravelPlanService
from src.components.travel_plan.domain.TravelPlanEntities import TravelPlan
from src.components.travel_plan.infrastructure.clients.OrsClient import ORSClient

logger = logging.getLogger(__name__)


class ReplanTripDayView:
    """Deterministic single-day re-optimisation for a trip (no LLM involved).

    Loads the trip's stored plan, re-solves the requested day using the
    orienteering solver with weather/opening-hours awareness, and persists the
    updated plan back to the trip.
    """

    @inject
    async def __call__(
        self,
        trip_id: int,
        day_number: int,
        get_trip: FromDishka[IGetTripQuery],
        update_plan: FromDishka[IUpdateGeneratedPlanCommand],
        payload: Optional[ReplanDayRequest] = Body(default=None),
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip = await get_trip.execute(current_user.id, trip_id)
        if not trip:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Trip not found')

        stored = trip.generated_plan or {}
        plan_dict = stored.get('plan_data') if isinstance(stored, dict) else None
        if not plan_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Trip has no generated plan to replan.',
            )

        try:
            plan = TravelPlan.from_dict(plan_dict)
        except Exception as e:
            logger.error(f'Failed to deserialize plan for trip {trip_id}: {e}')
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Stored plan is corrupted and cannot be replanned.',
            )

        # Parse current_datetime; default to now (UTC).
        request = payload or ReplanDayRequest()
        try:
            if request.current_datetime_iso:
                current_dt = datetime.fromisoformat(request.current_datetime_iso)
            else:
                current_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Invalid current_datetime_iso: {e}',
            )

        # Compute weather-based category modifiers (best-effort — silent on failure).
        category_modifiers = None
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
            logger.warning(f'Weather lookup failed for trip {trip_id} day {day_number}: {we}')

        service = TravelPlanService(ORSClient())
        try:
            updated = await service.replan_day(
                plan=plan,
                day_number=day_number,
                current_datetime=current_dt,
                visited_place_names=request.visited_place_names,
                category_modifiers=category_modifiers,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception as e:
            logger.error(f'Replan failed for trip {trip_id} day {day_number}: {e}', exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f'Replan failed: {e}',
            )

        # Preserve other top-level keys the agent may have added (plan_markdown, etc.).
        new_stored = dict(stored) if isinstance(stored, dict) else {}
        new_stored['plan_data'] = updated.to_dict()
        trip = await update_plan.execute(trip_id, new_stored)
        return TripResponse.model_validate(trip, from_attributes=True)
