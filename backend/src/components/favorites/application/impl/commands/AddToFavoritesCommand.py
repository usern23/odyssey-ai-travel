from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.favorites.application.core.commands.IAddToFavoritesCommand import IAddToFavoritesCommand
from src.components.favorites.infrastructure.models.FavoriteModel import Favorite


class AddToFavoritesCommand(IAddToFavoritesCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int, chat_id: int, custom_name: Optional[str] = None) -> Favorite:
        result = await self.db_session.execute(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.chat_id == chat_id))
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        favorite = Favorite(
            user_id=user_id,
            chat_id=chat_id,
            custom_name=custom_name)
        self.db_session.add(favorite)
        await self.db_session.commit()
        await self.db_session.refresh(favorite)
        return favorite
