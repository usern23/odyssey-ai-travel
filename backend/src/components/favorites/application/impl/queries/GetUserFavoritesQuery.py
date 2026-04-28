from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.components.chats.infrastructure.models import Chat
from src.components.favorites.application.core.queries.IGetUserFavoritesQuery import IGetUserFavoritesQuery
from src.components.favorites.infrastructure.models.FavoriteModel import Favorite


class GetUserFavoritesQuery(IGetUserFavoritesQuery):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int) -> List[Favorite]:
        result = await self.db_session.execute(
            select(Favorite)
            .options(selectinload(Favorite.chat).selectinload(Chat.trip))
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.created_at.desc()))
        return list(result.scalars().all())
