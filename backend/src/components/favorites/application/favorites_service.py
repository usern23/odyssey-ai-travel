from __future__ import annotations
from typing import List, Optional
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.components.chats.infrastructure.models import Chat
from src.components.favorites.infrastructure.models import Favorite
from src.components.trips.infrastructure.models import Trip


class FavoritesService:

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def add_to_favorites(
            self,
            user_id: int,
            chat_id: int,
            custom_name: Optional[str] = None) -> Favorite:
        existing = await self.get_favorite(user_id, chat_id)
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

    async def remove_from_favorites(self, user_id: int, chat_id: int) -> bool:
        result = await self.db_session.execute(delete(Favorite).where(Favorite.user_id == user_id, Favorite.chat_id == chat_id))
        await self.db_session.commit()
        return result.rowcount > 0

    async def get_favorite(
            self,
            user_id: int,
            chat_id: int) -> Optional[Favorite]:
        result = await self.db_session.execute(select(Favorite).where(Favorite.user_id == user_id, Favorite.chat_id == chat_id))
        return result.scalar_one_or_none()

    async def get_user_favorites(self, user_id: int) -> List[Favorite]:
        result = await self.db_session.execute(select(Favorite).options(selectinload(Favorite.chat).selectinload(Chat.trip)).where(Favorite.user_id == user_id).order_by(Favorite.created_at.desc()))
        return list(result.scalars().all())

    async def is_favorited(self, user_id: int, chat_id: int) -> bool:
        favorite = await self.get_favorite(user_id, chat_id)
        return favorite is not None

    async def update_custom_name(
            self,
            user_id: int,
            chat_id: int,
            custom_name: str) -> bool:
        favorite = await self.get_favorite(user_id, chat_id)
        if not favorite:
            return False
        favorite.custom_name = custom_name
        await self.db_session.commit()
        return True
