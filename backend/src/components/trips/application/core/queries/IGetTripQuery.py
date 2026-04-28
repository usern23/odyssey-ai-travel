from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class IGetTripQuery(ABC):
    @abstractmethod
    async def execute(self, user_id: int, trip_id: int) -> Optional[object]:
        ...
