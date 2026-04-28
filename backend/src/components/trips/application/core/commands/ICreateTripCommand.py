from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from datetime import date


class ICreateTripCommand(ABC):
    @abstractmethod
    async def execute(
        self,
        user_id: int,
        name: str,
        destination: Optional[str],
        origin: Optional[str],
        start_date: Optional[date],
        end_date: Optional[date],
        trip_profile: dict,
        generated_plan: dict,
    ) -> object:
        ...
