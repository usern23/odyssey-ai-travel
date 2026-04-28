from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from datetime import date


class IUpdateTripCommand(ABC):
    @abstractmethod
    async def execute(
        self,
        user_id: int,
        trip_id: int,
        name: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        trip_profile: Optional[dict] = None,
        generated_plan: Optional[dict] = None,
    ) -> object:
        ...
