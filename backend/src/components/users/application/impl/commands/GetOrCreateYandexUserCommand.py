from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.users.application.core.commands.IGetOrCreateYandexUserCommand import IGetOrCreateYandexUserCommand
from src.components.users.infrastructure.models.UserModel import User


class GetOrCreateYandexUserCommand(IGetOrCreateYandexUserCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, yandex_id: str, email: str) -> User:
        result = await self.db_session.execute(
            select(User).where(User.yandex_id == yandex_id))
        user = result.scalar_one_or_none()
        if user:
            return user
        result = await self.db_session.execute(
            select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            existing.yandex_id = yandex_id
            await self.db_session.commit()
            await self.db_session.refresh(existing)
            return existing
        user = User(email=email, yandex_id=yandex_id)
        self.db_session.add(user)
        await self.db_session.commit()
        await self.db_session.refresh(user)
        return user
