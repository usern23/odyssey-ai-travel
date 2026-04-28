from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class IGetUserProfileQuery(ABC):
    @abstractmethod
    async def __call__(self, user_id: int) -> Optional[Dict[str, Any]]:
        ...
