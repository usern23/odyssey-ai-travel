from __future__ import annotations

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.agent.application.AgentHostService import AgentHostService
from src.components.chats.application.core.commands import (
    IAddMessageCommand,
    ICreateChatCommand,
    IUpdateChatTitleCommand,
)
from src.components.chats.application.core.queries import (
    IGetChatQuery,
    IGetRecentMessagesQuery,
    IGetUserProfileQuery,
)


class _AgentProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def agent_host_service(
        self,
        db_session: AsyncSession,
        get_chat_query: IGetChatQuery,
        add_message_command: IAddMessageCommand,
        get_recent_messages_query: IGetRecentMessagesQuery,
        get_user_profile_query: IGetUserProfileQuery,
        update_chat_title_command: IUpdateChatTitleCommand,
        create_chat_command: ICreateChatCommand,
    ) -> AgentHostService:
        return AgentHostService(
            db_session=db_session,
            get_chat_query=get_chat_query,
            add_message_command=add_message_command,
            get_recent_messages_query=get_recent_messages_query,
            get_user_profile_query=get_user_profile_query,
            update_chat_title_command=update_chat_title_command,
            create_chat_command=create_chat_command,
        )


class AgentApplication:

    def __call__(self) -> Provider:
        return _AgentProvider()
