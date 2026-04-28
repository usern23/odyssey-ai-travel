from abc import ABC, abstractmethod
from typing import Optional
from src.components.users.infrastructure.models.UserProfileModel import UserProfile
from src.components.users.web.models.UserProfileUpdateRequest import UserProfileUpdateRequest


class IUpdateProfileCommand(ABC):
    @abstractmethod
    async def __call__(self, user_id: int, payload: UserProfileUpdateRequest) -> Optional[UserProfile]:
        ...
