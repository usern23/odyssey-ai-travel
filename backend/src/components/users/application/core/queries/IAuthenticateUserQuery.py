from abc import ABC, abstractmethod
from typing import Optional
from src.components.users.infrastructure.models.UserModel import User


class IAuthenticateUserQuery(ABC):
    @abstractmethod
    async def __call__(self, email: str, password: str) -> Optional[User]:
        ...
