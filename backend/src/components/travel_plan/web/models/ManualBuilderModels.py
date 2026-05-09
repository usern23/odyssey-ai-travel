"""Pydantic DTOs for the manual trip-builder REST API.

All mutating requests carry an optional ``expected_version`` for
optimistic locking (set to the version returned by the previous read).
A mismatch yields HTTP 409.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Reusable place payload ──────────────────────────────────────────
class PlacePayload(BaseModel):
    """User-supplied place. Mirrors Place.from_dict's expectations."""
    name: str
    lat: float
    lon: float
    category: str = 'other'
    visit_duration_min: int = 60
    opening_hours: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    price_level: Optional[int] = None
    source: Optional[str] = None


# ── Versioned mixin (we duplicate the field for clarity in OpenAPI) ─
class _Versioned(BaseModel):
    expected_version: Optional[int] = Field(
        default=None,
        description='Plan version observed by the client. If provided '
        'and different from the server version, request is rejected '
        'with 409 Conflict.',
    )


# ── Trip / day setup ────────────────────────────────────────────────
class CreateManualTripRequest(BaseModel):
    name: str
    destination: str = Field(
        ...,
        min_length=1,
        description='City / country, used to geocode a default starting '
        'point if no hotel is supplied.',
    )
    origin: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    hotel: Optional[PlacePayload] = Field(
        default=None,
        description='Optional starting point. If omitted, the server '
        'geocodes `destination` and uses its centre as a placeholder '
        '(“Центр {destination}”).',
    )
    start_hour: int = Field(default=10, ge=0, le=23,
                            description='Час начала активного дня (0..23).')
    end_hour: int = Field(default=22, ge=1, le=24,
                          description='Час окончания активного дня (1..24).')
    trip_profile: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('end_hour')
    @classmethod
    def _check_end_after_start(cls, v: int, info: Any) -> int:
        start = (info.data or {}).get('start_hour', 10)
        if v <= start:
            raise ValueError('end_hour должен быть больше start_hour')
        return v


# ── Day CRUD ────────────────────────────────────────────────────────
class AddPlaceRequest(_Versioned):
    place: PlacePayload
    index: Optional[int] = Field(
        default=None,
        description='Position within the day. None appends to the end.',
    )
    is_locked: bool = False
    note: Optional[str] = None
    actual_cost: Optional[float] = None


class UpdateActivityRequest(_Versioned):
    note: Optional[str] = None
    actual_cost: Optional[float] = None
    is_locked: Optional[bool] = None
    visit_duration_min: Optional[int] = None


class ReorderDayRequest(_Versioned):
    new_indices: List[int] = Field(
        ...,
        description='Permutation of 0..N-1 representing the new order '
        'of activities within the day.',
    )


class MovePlaceRequest(_Versioned):
    from_day: int
    to_day: int
    activity_index: int
    target_index: Optional[int] = None


# ── Wishlist ────────────────────────────────────────────────────────
class WishlistAddRequest(_Versioned):
    place: PlacePayload


class PromoteWishlistRequest(_Versioned):
    day_number: int
    target_index: Optional[int] = None


# ── Budget ──────────────────────────────────────────────────────────
class UpdateBudgetRequest(_Versioned):
    total: Optional[float] = None
    by_category: Optional[Dict[str, float]] = None
    currency: Optional[str] = None
    lodging_total: Optional[float] = None
    transport_total: Optional[float] = None

# ── Hotel ───────────────────────────────────────────────────────────
class UpdateHotelRequest(_Versioned):
    hotel: Optional[PlacePayload] = Field(
        default=None,
        description='New hotel/accommodation. Send null to clear; server '
        'will geocode the trip destination and use its centre as a '
        'placeholder, mirroring the manual-create flow.',
    )


# ── Optimisation / search / ask-ai ──────────────────────────────────
class OptimizeDayRequest(_Versioned):
    """No body fields beyond optimistic-lock token for now."""


class SearchPlacesRequest(BaseModel):
    query: str
    near_lat: Optional[float] = None
    near_lon: Optional[float] = None
    radius_km: Optional[float] = Field(
        default=50.0,
        ge=0,
        le=1000,
        description='Hard filter radius around (near_lat, near_lon). Set '
        'to 0 or null to disable and search globally (focus.point still '
        'ranks nearer results higher).',
    )
    limit: int = 10


class AskAiRequest(BaseModel):
    initial_message: Optional[str] = None
