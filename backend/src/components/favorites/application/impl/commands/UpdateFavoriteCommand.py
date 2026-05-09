from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.favorites.application.core.commands.IUpdateFavoriteCommand import IUpdateFavoriteCommand
from src.components.favorites.infrastructure.models.FavoriteModel import Favorite


class UpdateFavoriteCommand(IUpdateFavoriteCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int, trip_id: int, custom_name: str) -> bool:
        result = await self.db_session.execute(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.trip_id == trip_id))
        favorite = result.scalar_one_or_none()
        if not favorite:
            return False
        favorite.custom_name = custom_name
        await self.db_session.commit()
        return True
