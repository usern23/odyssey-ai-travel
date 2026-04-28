from dishka import Provider, Scope
from src.components.chats.application.core.commands import (
    ICreateChatCommand,
    IUpdateChatTitleCommand,
    ILinkTripToChatCommand,
    IDeleteChatCommand,
    IAddMessageCommand,
)
from src.components.chats.application.core.queries import (
    IGetChatQuery,
    IGetChatWithMessagesQuery,
    IGetUserChatsQuery,
    IGetRecentMessagesQuery,
    IGetUserProfileQuery,
)
from src.components.chats.application.impl.commands import (
    CreateChatCommand,
    UpdateChatTitleCommand,
    LinkTripToChatCommand,
    DeleteChatCommand,
    AddMessageCommand,
)
from src.components.chats.application.impl.queries import (
    GetChatQuery,
    GetChatWithMessagesQuery,
    GetUserChatsQuery,
    GetRecentMessagesQuery,
    GetUserProfileQuery,
)

__all__ = ['ChatsApplication']


class ChatsApplication:
    def __call__(self) -> Provider:
        provider = Provider(scope=Scope.REQUEST)

        provider.provide(CreateChatCommand, provides=ICreateChatCommand)
        provider.provide(UpdateChatTitleCommand, provides=IUpdateChatTitleCommand)
        provider.provide(LinkTripToChatCommand, provides=ILinkTripToChatCommand)
        provider.provide(DeleteChatCommand, provides=IDeleteChatCommand)
        provider.provide(AddMessageCommand, provides=IAddMessageCommand)

        provider.provide(GetChatQuery, provides=IGetChatQuery)
        provider.provide(GetChatWithMessagesQuery, provides=IGetChatWithMessagesQuery)
        provider.provide(GetUserChatsQuery, provides=IGetUserChatsQuery)
        provider.provide(GetRecentMessagesQuery, provides=IGetRecentMessagesQuery)
        provider.provide(GetUserProfileQuery, provides=IGetUserProfileQuery)

        return provider
