from __future__ import annotations

from abc import ABC, abstractmethod


class IUpdateGeneratedPlanCommand(ABC):
    @abstractmethod
    async def execute(self, trip_id: int, plan: dict) -> object:
        ...
