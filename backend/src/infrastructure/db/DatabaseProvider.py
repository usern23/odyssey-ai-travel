from collections.abc import AsyncIterator
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.db.session import async_session_factory


class DatabaseProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        async with async_session_factory() as session:
            yield session
