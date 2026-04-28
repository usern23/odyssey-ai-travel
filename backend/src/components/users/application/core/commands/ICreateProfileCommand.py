from abc import ABC, abstractmethod
from src.components.users.infrastructure.models.UserProfileModel import UserProfile
from src.components.users.web.models.UserProfileCreateRequest import UserProfileCreateRequest


class ICreateProfileCommand(ABC):
    @abstractmethod
    async def __call__(self, user_id: int, payload: UserProfileCreateRequest) -> UserProfile:
        ...
