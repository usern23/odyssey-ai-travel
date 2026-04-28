from __future__ import annotations

from fastapi import FastAPI

from src.components.agent.web.models.AgentChatResponse import AgentChatResponse
from src.components.agent.web.views.AgentChatView import AgentChatView


class AgentWebRouter:

    def __call__(self, app: FastAPI, prefix: str = ''):
        app.add_api_route(
            f'{prefix}/agent/chat',
            AgentChatView(),
            methods=['POST'],
            response_model=AgentChatResponse,
            tags=['agent'],
        )
