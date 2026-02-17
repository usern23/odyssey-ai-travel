from __future__ import annotations
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.web.dependencies import get_current_user
from src.components.trips.web.models.dto import TripCreate, TripRead
from src.components.trips.application.services import TripService
from src.components.users.infrastructure.models import User
from src.infrastructure.db.session import get_db_session
router = APIRouter(prefix='/trips', tags=['trips'])


@router.post('/', response_model=TripRead, status_code=status.HTTP_201_CREATED)
async def create_trip(
        payload: TripCreate,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> TripRead:
    service = TripService(session)
    trip = await service.create_trip(current_user.id, payload)
    return TripRead.model_validate(trip, from_attributes=True)


@router.get('/', response_model=List[TripRead])
async def list_trips(
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> List[TripRead]:
    service = TripService(session)
    trips = await service.list_trips(current_user.id)
    return [
        TripRead.model_validate(
            trip,
            from_attributes=True) for trip in trips]
