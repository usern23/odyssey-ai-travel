from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ReplanDayRequest(BaseModel):
    """Request to re-optimise a single day of an existing trip plan.

    All fields are optional — omitting them means: use "now" as the cut-off
    time and keep every already scheduled place in play.
    """

    current_datetime_iso: Optional[str] = Field(
        default=None,
        description="Cut-off timestamp in ISO-8601 (e.g. '2025-06-15T13:30:00'). "
                    "Only places reachable after this moment are kept/scheduled. "
                    "Defaults to the server's current UTC time.",
    )
    visited_place_names: Optional[List[str]] = Field(
        default=None,
        description="Names of POIs the user has already visited today and that "
                    "should be excluded from the replanned day.",
    )
