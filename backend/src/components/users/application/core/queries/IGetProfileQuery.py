from abc import ABC, abstractmethod
from typing import Optional
from src.components.users.infrastructure.models.UserProfileModel import UserProfile


class IGetProfileQuery(ABC):
    @abstractmethod
    async def __call__(self, user_id: int) -> Optional[UserProfile]:
        ...
