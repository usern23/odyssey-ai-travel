from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.favorites.application.core.queries.IIsFavoritedQuery import IIsFavoritedQuery
from src.components.favorites.infrastructure.models.FavoriteModel import Favorite


class IsFavoritedQuery(IIsFavoritedQuery):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int, chat_id: int) -> bool:
        result = await self.db_session.execute(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.chat_id == chat_id))
        return result.scalar_one_or_none() is not None
