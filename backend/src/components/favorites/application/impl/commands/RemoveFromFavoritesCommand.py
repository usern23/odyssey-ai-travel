from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.favorites.application.core.commands.IRemoveFromFavoritesCommand import IRemoveFromFavoritesCommand
from src.components.favorites.infrastructure.models.FavoriteModel import Favorite


class RemoveFromFavoritesCommand(IRemoveFromFavoritesCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int, trip_id: int) -> bool:
        result = await self.db_session.execute(
            delete(Favorite).where(Favorite.user_id == user_id, Favorite.trip_id == trip_id))
        await self.db_session.commit()
        return result.rowcount > 0
