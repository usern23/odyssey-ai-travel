from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.users.application.core.commands.IRegisterUserCommand import IRegisterUserCommand
from src.components.users.infrastructure.models.UserModel import User
from src.components.users.web.models.UserCreateRequest import UserCreateRequest
from src.infrastructure.auth import get_password_hash


class UserAlreadyExistsError(Exception):
    pass


class RegisterUserCommand(IRegisterUserCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, payload: UserCreateRequest) -> User:
        user = User(
            email=payload.email,
            hashed_password=get_password_hash(payload.password),
            timezone=payload.timezone)
        self.db_session.add(user)
        try:
            await self.db_session.commit()
        except IntegrityError as exc:
            await self.db_session.rollback()
            raise UserAlreadyExistsError from exc
        await self.db_session.refresh(user)
        return user
