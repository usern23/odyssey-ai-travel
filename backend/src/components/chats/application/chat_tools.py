from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from src.common.events.rabbitmq import publish_event
from src.common.events.types import AddToFavoritesEvent, ChatTitleUpdateEvent


@dataclass
class ChatManager:
    chat_id: int
    user_id: int

    async def generate_title(self, title: str) -> str:
        if not title or len(title.strip()) == 0:
            return 'Ошибка: название не может быть пустым'
        title = title.strip()[:100]
        await publish_event(ChatTitleUpdateEvent(chat_id=self.chat_id, title=title))
        return f'Название чата обновлено: {title}'

    async def add_to_favorites(self, custom_name: Optional[str] = None) -> str:
        await publish_event(AddToFavoritesEvent(user_id=self.user_id, chat_id=self.chat_id, custom_name=custom_name))
        return 'План путешествия добавлен в избранное ⭐'


def get_chat_tools_description() -> str:
    return '\n## Инструменты управления чатом\n\n### generate_title\nГенерирует название для чата после первого сообщения пользователя.\n- Вызывай СРАЗУ после первого сообщения пользователя\n- Название должно быть коротким (3-5 слов) и отражать тему разговора\n- Пример: "Поездка в Питер на выходные"\n\n### add_to_favorites\nДобавляет текущий план в избранное пользователя.\n- Вызывай ТОЛЬКО когда пользователь явно просит сохранить план\n'
