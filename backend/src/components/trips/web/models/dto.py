from __future__ import annotations
from datetime import date
from typing import Optional
from geoalchemy2.shape import to_shape
from pydantic import BaseModel, Field


class TripBase(BaseModel):
    name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    trip_profile: dict = Field(default_factory=dict)
    generated_plan: dict = Field(default_factory=dict)


class TripCreate(TripBase):
    pass


class TripRead(TripBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True


class TripList(BaseModel):
    items: list[TripRead]
    total: int


class TripUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    trip_profile: Optional[dict] = None
    generated_plan: Optional[dict] = None


class PointOfInterestRead(BaseModel):
    id: int
    name: str
    city: str
    description: Optional[str] = None
    tags: dict
    latitude: float
    longitude: float

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        geometry = to_shape(obj.location)
        return cls(
            id=obj.id,
            name=obj.name,
            city=obj.city,
            description=obj.description,
            tags=obj.tags,
            latitude=geometry.y,
            longitude=geometry.x)
