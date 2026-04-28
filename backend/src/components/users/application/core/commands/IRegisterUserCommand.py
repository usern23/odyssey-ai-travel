from abc import ABC, abstractmethod
from src.components.users.infrastructure.models.UserModel import User
from src.components.users.web.models.UserCreateRequest import UserCreateRequest


class IRegisterUserCommand(ABC):
    @abstractmethod
    async def __call__(self, payload: UserCreateRequest) -> User:
        ...
