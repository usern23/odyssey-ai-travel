from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class IListUserTripsQuery(ABC):
    @abstractmethod
    async def execute(self, user_id: int) -> List[object]:
        ...
