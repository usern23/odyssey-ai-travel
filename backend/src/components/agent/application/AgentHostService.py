from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.configs import settings
from src.common.events.rabbitmq import publish_event
from src.common.events.types import (
    AgentProcessingCompletedEvent,
    AgentProcessingStartedEvent,
    ChatTitleUpdateEvent,
    MessageSavedEvent,
    ToolExecutedEvent,
)
from src.components.agent.infrastructure.LangGraphAgent import LangGraphAgent
from src.components.agent.infrastructure.tools import ToolsManager
from src.components.agent.web.models.AgentChatResponse import AgentChatResponse
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
from src.components.chats.infrastructure.models import MessageRole

logger = logging.getLogger(__name__)


class AgentHostService:

    def __init__(
        self,
        db_session: AsyncSession,
        get_chat_query: IGetChatQuery,
        add_message_command: IAddMessageCommand,
        get_recent_messages_query: IGetRecentMessagesQuery,
        get_user_profile_query: IGetUserProfileQuery,
        update_chat_title_command: IUpdateChatTitleCommand,
        create_chat_command: ICreateChatCommand,
        tools_manager: Optional[ToolsManager] = None,
        publish_events: bool = True,
    ):
        self._db_session = db_session
        self._get_chat = get_chat_query
        self._add_message = add_message_command
        self._get_recent_messages = get_recent_messages_query
        self._get_user_profile = get_user_profile_query
        self._update_chat_title = update_chat_title_command
        self._create_chat = create_chat_command
        self._base_tools_manager = tools_manager
        self._publish_events = publish_events
        self._current_chat_id: Optional[int] = None
        self._agent: Optional[LangGraphAgent] = None

    def _get_tools_manager(self, chat_id: int) -> ToolsManager:
        if self._base_tools_manager:
            self._base_tools_manager.chat_id = chat_id
            return self._base_tools_manager
        return ToolsManager(self._db_session, chat_id=chat_id)

    def _get_agent(self, chat_id: int) -> LangGraphAgent:
        if self._agent is None or self._current_chat_id != chat_id:
            tools_manager = self._get_tools_manager(chat_id)
            self._agent = LangGraphAgent(
                tools=tools_manager.get_langchain_tools())
            self._current_chat_id = chat_id
        return self._agent

    async def _publish(self, event) -> None:
        if self._publish_events:
            await publish_event(event)
        else:
            logger.debug(
                f'Event publishing disabled, skipping: {event.event_type}')

    async def _load_context(self, user_id: int, chat) -> Dict[str, Any]:
        profile = await self._get_user_profile(user_id)
        recent_messages = await self._load_recent_messages(chat.id)
        trip = getattr(chat, 'trip', None)
        trip_info = None
        if trip:
            generated_plan = getattr(trip, 'generated_plan', None) or {}
            days = generated_plan.get('days') or []
            trip_info = {
                'id': trip.id,
                'destination': trip.destination,
                'origin': trip.origin,
                'start_date': trip.start_date.isoformat() if trip.start_date else None,
                'end_date': trip.end_date.isoformat() if trip.end_date else None,
                'budget': trip.trip_profile.get('budget') if trip.trip_profile else None,
                'has_plan': bool(generated_plan),
                'plan_days': len(days),
                'plan_total_places': generated_plan.get('total_places'),
                'plan_hotel_name': (generated_plan.get('hotel') or {}).get('name'),
            }
        return {
            'user_id': user_id,
            'chat_id': chat.id,
            'user_profile': profile,
            'chat': {'id': chat.id, 'title': chat.title},
            'trip': trip_info,
            'recent_messages': recent_messages,
        }

    async def _load_recent_messages(
        self, chat_id: int, limit: int = 10
    ) -> List[Any]:
        messages = await self._get_recent_messages(chat_id, limit)
        lc_messages = []
        for msg in messages:
            if msg.role == MessageRole.USER:
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == MessageRole.ASSISTANT:
                lc_messages.append(AIMessage(content=msg.content))
        return lc_messages

    async def _maybe_generate_title(
        self, chat, user_message: str
    ) -> Optional[str]:
        if chat.title != 'Новый чат':
            return None
        # Save fallback title synchronously so list_chats immediately shows
        # something meaningful, even if the LLM title generation fails or is
        # still in flight.
        fallback = self._fallback_title(user_message)
        await self._update_chat_title(chat.id, fallback)
        await self._publish(
            ChatTitleUpdateEvent(chat_id=chat.id, title=fallback))
        logger.info(
            f'Set fallback title for chat {chat.id}: {fallback}')
        # Kick off LLM-based title generation in the background. The task
        # only calls the LLM and publishes a ChatTitleUpdateEvent; the
        # chat_worker consumer updates the DB, so we do not need the
        # current request-scoped session to stay alive.
        if settings.llm_generate_titles:
            asyncio.create_task(
                self._background_llm_title(chat.id, user_message))
        return fallback

    async def _background_llm_title(
        self, chat_id: int, user_message: str
    ) -> None:
        try:
            title = await LangGraphAgent.generate_title(user_message)
            if title:
                await publish_event(
                    ChatTitleUpdateEvent(chat_id=chat_id, title=title))
                logger.info(
                    f'Background LLM title generated for chat {chat_id}: {title}')
        except Exception as e:
            logger.warning(
                f'Background LLM title generation failed for chat {chat_id}: {e}')

    def _fallback_title(self, user_message: str) -> str:
        compact = ' '.join(user_message.strip().split())
        if not compact:
            return 'Новый чат'
        words = compact.split(' ')
        title = ' '.join(words[:6])
        return (title[:77] + '...') if len(title) > 80 else title

    async def _extract_travel_context(
        self, chat_id: int, tool_results: List[Dict[str, Any]]
    ) -> None:
        destination = None
        for result in tool_results:
            tool_name = result.get('name', '')
            data = result.get('result', {})
            if not isinstance(data, dict):
                continue
            if tool_name in ('destination_suggester', 'suggest_flights'):
                recs = data.get('recommendations', [])
                if recs and isinstance(recs[0], dict) and ('city' in recs[0]):
                    destination = recs[0]['city']
        if destination:
            logger.info(
                f"Detected destination '{destination}' in chat {chat_id} (managed via Trip)")

    async def process_message(
        self, user_id: int, chat_id: int, message: str
    ) -> AgentChatResponse:
        start_time = time.time()
        chat = await self._get_chat(chat_id, user_id)
        if not chat:
            raise ValueError(f'Chat {chat_id} not found for user {user_id}')
        await self._publish(
            AgentProcessingStartedEvent(
                chat_id=chat_id, user_id=user_id, message=message))
        await self._add_message(chat_id, MessageRole.USER, message)
        await self._publish(
            MessageSavedEvent(
                chat_id=chat_id, role=MessageRole.USER.value, content=message))
        new_title = await self._maybe_generate_title(chat, message)
        context = await self._load_context(user_id, chat)
        logger.debug(
            f"Processing message for chat {chat_id}, context: {context.get('chat')}")
        agent = self._get_agent(chat_id)
        response = await agent.ainvoke(message=message, context=context)
        reply = response['reply']
        history = response['history']
        llm_turns = sum(1 for msg in history if isinstance(msg, AIMessage))
        tool_results: List[Dict[str, Any]] = []
        for msg in history:
            if isinstance(msg, ToolMessage):
                content = msg.content
                result_data = content
                if isinstance(content, str):
                    try:
                        result_data = json.loads(content)
                    except json.JSONDecodeError:
                        pass
                tool_results.append(
                    {'name': msg.name, 'result': result_data})
                await self._publish(
                    ToolExecutedEvent(
                        chat_id=chat_id,
                        tool_name=msg.name or 'unknown',
                        tool_input='',
                        tool_output=content
                        if isinstance(content, str)
                        else json.dumps(result_data),
                        execution_time_ms=0,
                    ))
        if isinstance(reply, str) and reply:
            await self._add_message(
                chat_id, MessageRole.ASSISTANT, reply)
            await self._publish(
                MessageSavedEvent(
                    chat_id=chat_id,
                    role=MessageRole.ASSISTANT.value,
                    content=reply,
                ))
        await self._extract_travel_context(chat_id, tool_results)
        processing_time_ms = int((time.time() - start_time) * 1000)
        await self._publish(
            AgentProcessingCompletedEvent(
                chat_id=chat_id,
                user_id=user_id,
                reply=reply,
                tool_calls=json.dumps(
                    [t['name'] for t in tool_results])
                if tool_results
                else None,
            ))
        logger.info(
            f'Agent processed message for chat {chat_id} in {processing_time_ms}ms')
        metadata = {
            'tool_results': tool_results,
            'llm_profile': {
                'llm_turns': llm_turns,
                'tool_calls': len(tool_results),
            },
        }
        logger.info(
            'LLM profile chat=%s turns=%s tool_calls=%s',
            chat_id,
            llm_turns,
            len(tool_results),
        )
        return AgentChatResponse(
            reply=reply, chat_id=chat_id, metadata=metadata)

    async def stream_message(
        self, user_id: int, chat_id: int, message: str
    ) -> AsyncIterator[Dict[str, Any]]:
        chat = await self._get_chat(chat_id, user_id)
        if not chat:
            raise ValueError(f'Chat {chat_id} not found for user {user_id}')
        await self._add_message(chat_id, MessageRole.USER, message)
        new_title = await self._maybe_generate_title(chat, message)
        if new_title:
            yield {
                'event': 'title',
                'data': json.dumps(
                    {'chat_id': chat_id, 'title': new_title}),
            }
        context = await self._load_context(user_id, chat)
        agent = self._get_agent(chat_id)
        full_reply = ''
        tool_results: List[Dict[str, Any]] = []
        async for chunk in agent.astream(message=message, context=context):
            if chunk['type'] == 'token':
                full_reply += chunk['content']
                yield {
                    'event': 'token',
                    'data': json.dumps({'content': chunk['content']}),
                }
            elif chunk['type'] == 'tool_start':
                yield {
                    'event': 'tool_start',
                    'data': json.dumps({'tool': chunk['content']}),
                }
            elif chunk['type'] == 'tool_end':
                tool_name = chunk['content']
                tool_output = chunk.get('output', '')
                yield {
                    'event': 'tool_end',
                    'data': json.dumps({'tool': tool_name}),
                }
                if tool_name == 'show_route_map' and '❌' not in str(
                    tool_output
                ):
                    yield {
                        'event': 'map_ready',
                        'data': json.dumps({'chat_id': chat_id}),
                    }
                result_data = tool_output
                if isinstance(tool_output, str):
                    try:
                        result_data = json.loads(tool_output)
                    except (json.JSONDecodeError, TypeError):
                        pass
                tool_results.append(
                    {'name': tool_name, 'result': result_data})
                await self._publish(
                    ToolExecutedEvent(
                        chat_id=chat_id,
                        tool_name=tool_name or 'unknown',
                        tool_input='',
                        tool_output=tool_output
                        if isinstance(tool_output, str)
                        else json.dumps(result_data, default=str),
                        execution_time_ms=0,
                    ))
        if full_reply:
            await self._add_message(
                chat_id, MessageRole.ASSISTANT, full_reply)
        await self._extract_travel_context(chat_id, tool_results)
        yield {
            'event': 'done',
            'data': json.dumps(
                {'chat_id': chat_id, 'reply': full_reply}),
        }

    async def create_chat_and_process(
        self, user_id: int, message: str
    ) -> tuple:
        chat = await self._create_chat(user_id)
        response = await self.process_message(user_id, chat.id, message)
        return (chat, response)
