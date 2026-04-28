from abc import ABC, abstractmethod
from src.components.users.infrastructure.models.UserModel import User


class IGetOrCreateYandexUserCommand(ABC):
    @abstractmethod
    async def __call__(self, yandex_id: str, email: str) -> User:
        ...
