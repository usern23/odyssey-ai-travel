from __future__ import annotations

from abc import ABC, abstractmethod


class IDeleteTripCommand(ABC):
    @abstractmethod
    async def execute(self, user_id: int, trip_id: int) -> bool:
        ...
