from __future__ import annotations
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.components.chats.infrastructure.models import Chat, ChatMessage, ChatStatus, MessageRole
from src.components.users.infrastructure.models import User, UserProfile


class ChatService:

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def create_chat(self, user_id: int) -> Chat:
        chat = Chat(
            user_id=user_id,
            title='Новый чат',
            status=ChatStatus.ACTIVE)
        self.db_session.add(chat)
        await self.db_session.commit()
        await self.db_session.refresh(chat)
        return chat

    async def get_chat(self, chat_id: int, user_id: int) -> Optional[Chat]:
        result = await self.db_session.execute(select(Chat).options(selectinload(Chat.trip)).where(Chat.id == chat_id, Chat.user_id == user_id, Chat.status != ChatStatus.DELETED))
        return result.scalar_one_or_none()

    async def get_chat_with_messages(
            self,
            chat_id: int,
            user_id: int) -> Optional[Chat]:
        result = await self.db_session.execute(select(Chat).options(selectinload(Chat.messages), selectinload(Chat.trip)).where(Chat.id == chat_id, Chat.user_id == user_id, Chat.status != ChatStatus.DELETED))
        return result.scalar_one_or_none()

    async def get_user_chats(
            self,
            user_id: int,
            limit: int = 50) -> List[Chat]:
        result = await self.db_session.execute(select(Chat).options(selectinload(Chat.trip)).where(Chat.user_id == user_id, Chat.status != ChatStatus.DELETED).order_by(Chat.updated_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def update_chat_title(self, chat_id: int, title: str) -> None:
        await self.db_session.execute(update(Chat).where(Chat.id == chat_id).values(title=title))
        await self.db_session.commit()

    async def link_trip_to_chat(self, chat_id: int, trip_id: int) -> None:
        await self.db_session.execute(update(Chat).where(Chat.id == chat_id).values(trip_id=trip_id))
        await self.db_session.commit()

    async def archive_chat(self, chat_id: int, user_id: int) -> bool:
        result = await self.db_session.execute(update(Chat).where(Chat.id == chat_id, Chat.user_id == user_id).values(status=ChatStatus.ARCHIVED))
        await self.db_session.commit()
        return result.rowcount > 0

    async def delete_chat(self, chat_id: int, user_id: int) -> bool:
        result = await self.db_session.execute(update(Chat).where(Chat.id == chat_id, Chat.user_id == user_id).values(status=ChatStatus.DELETED))
        await self.db_session.commit()
        return result.rowcount > 0

    async def add_message(
            self,
            chat_id: int,
            role: MessageRole,
            content: str,
            tool_name: Optional[str] = None,
            tool_call_id: Optional[str] = None) -> ChatMessage:
        message = ChatMessage(
            chat_id=chat_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id)
        self.db_session.add(message)
        await self.db_session.commit()
        await self.db_session.refresh(message)
        return message

    async def get_recent_messages(
            self,
            chat_id: int,
            limit: int = 20) -> List[ChatMessage]:
        result = await self.db_session.execute(select(ChatMessage).where(ChatMessage.chat_id == chat_id).order_by(ChatMessage.created_at.desc()).limit(limit))
        return list(reversed(result.scalars().all()))

    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        result = await self.db_session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        return {
            'user_id': profile.user_id,
            'travel_style': profile.travel_style.value,
            'primary_interests': profile.primary_interests,
            'budget_preference': profile.budget_preference.value,
            'preferred_activities': profile.preferred_activities,
            'disliked_activities': profile.disliked_activities}
