from fastapi import FastAPI, status
from src.components.chats.web.views.CreateChatView import CreateChatView
from src.components.chats.web.views.ListChatsView import ListChatsView
from src.components.chats.web.views.GetChatView import GetChatView
from src.components.chats.web.views.SendMessageView import SendMessageView
from src.components.chats.web.views.StreamMessageView import StreamMessageView
from src.components.chats.web.views.StreamNewChatView import StreamNewChatView
from src.components.chats.web.views.UpdateChatView import UpdateChatView
from src.components.chats.web.views.GetRouteMapView import GetRouteMapView
from src.components.chats.web.views.DeleteChatView import DeleteChatView
from src.components.chats.web.models.AgentReplyResponse import AgentReplyResponse
from src.components.chats.web.models.ChatListResponse import ChatListResponse
from src.components.chats.web.models.ChatWithMessagesResponse import ChatWithMessagesResponse
from src.components.chats.web.models.ChatResponse import ChatResponse

__all__ = ['ChatsWebRouter']


class ChatsWebRouter:

    def __call__(self, app: FastAPI, prefix: str = ''):
        app.add_api_route(
            path=f'{prefix}/chats',
            methods=['POST'],
            tags=['chats'],
            response_model=AgentReplyResponse,
            status_code=status.HTTP_201_CREATED,
            endpoint=CreateChatView().__call__)

        app.add_api_route(
            path=f'{prefix}/chats',
            methods=['GET'],
            tags=['chats'],
            response_model=ChatListResponse,
            endpoint=ListChatsView().__call__)

        app.add_api_route(
            path=f'{prefix}/chats/{{chat_id}}',
            methods=['GET'],
            tags=['chats'],
            response_model=ChatWithMessagesResponse,
            endpoint=GetChatView().__call__)

        app.add_api_route(
            path=f'{prefix}/chats/{{chat_id}}/messages',
            methods=['POST'],
            tags=['chats'],
            response_model=AgentReplyResponse,
            endpoint=SendMessageView().__call__)

        app.add_api_route(
            path=f'{prefix}/chats/{{chat_id}}/stream',
            methods=['POST'],
            tags=['chats'],
            endpoint=StreamMessageView().__call__)

        app.add_api_route(
            path=f'{prefix}/chats/stream',
            methods=['POST'],
            tags=['chats'],
            status_code=status.HTTP_201_CREATED,
            endpoint=StreamNewChatView().__call__)

        app.add_api_route(
            path=f'{prefix}/chats/{{chat_id}}',
            methods=['PATCH'],
            tags=['chats'],
            response_model=ChatResponse,
            endpoint=UpdateChatView().__call__)

        app.add_api_route(
            path=f'{prefix}/chats/{{chat_id}}/route-map',
            methods=['GET'],
            tags=['chats'],
            endpoint=GetRouteMapView().__call__)

        app.add_api_route(
            path=f'{prefix}/chats/{{chat_id}}',
            methods=['DELETE'],
            tags=['chats'],
            endpoint=DeleteChatView().__call__)
