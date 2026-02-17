from __future__ import annotations
import json
import logging
import time
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.events.rabbitmq import publish_event
from src.common.events.types import AgentProcessingCompletedEvent, AgentProcessingStartedEvent, ChatTitleUpdateEvent, MessageSavedEvent, ToolExecutedEvent, TravelPlanGeneratedEvent, TripDataCollectedEvent
from src.components.agent.infrastructure.langgraph_host import LangGraphAgent
from src.components.agent.infrastructure.tools import ToolsManager
from src.components.agent.web.models.dto import AgentChatResponse
from src.components.chats.application.chat_service import ChatService
from src.components.chats.infrastructure.models import Chat, MessageRole
logger = logging.getLogger(__name__)


class AgentHostServiceV3:

    def __init__(
            self,
            db_session: AsyncSession,
            tools_manager: Optional[ToolsManager] = None,
            publish_events: bool = True):
        self.db_session = db_session
        self.chat_service = ChatService(db_session)
        self._base_tools_manager = tools_manager
        self._publish_events = publish_events
        self._current_chat_id: Optional[int] = None
        self._agent: Optional[LangGraphAgent] = None

    def _get_tools_manager(self, chat_id: int) -> ToolsManager:
        if self._base_tools_manager:
            self._base_tools_manager.chat_id = chat_id
            return self._base_tools_manager
        return ToolsManager(self.db_session, chat_id=chat_id)

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
                f'Event publishing disabled, skipping: {
                    event.event_type}')

    async def _load_context(self, user_id: int, chat: Chat) -> Dict[str, Any]:
        profile = await self.chat_service.get_user_profile(user_id)
        recent_messages = await self._load_recent_messages(chat.id)
        trip = getattr(chat, 'trip', None)
        trip_info = None
        if trip:
            trip_info = {
                'id': trip.id,
                'destination': trip.destination,
                'origin': trip.origin,
                'start_date': trip.start_date.isoformat() if trip.start_date else None,
                'end_date': trip.end_date.isoformat() if trip.end_date else None,
                'budget': trip.trip_profile.get('budget') if trip.trip_profile else None}
        return {
            'user_id': user_id,
            'chat_id': chat.id,
            'user_profile': profile,
            'chat': {
                'id': chat.id,
                'title': chat.title},
            'trip': trip_info,
            'recent_messages': recent_messages}

    async def _load_recent_messages(
            self,
            chat_id: int,
            limit: int = 10) -> List[Any]:
        messages = await self.chat_service.get_recent_messages(chat_id, limit)
        lc_messages = []
        for msg in messages:
            if msg.role == MessageRole.USER:
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == MessageRole.ASSISTANT:
                lc_messages.append(AIMessage(content=msg.content))
        return lc_messages

    async def _maybe_generate_title(
            self,
            chat: Chat,
            user_message: str) -> Optional[str]:
        if chat.title == 'Новый чат':
            title = user_message[:50].strip()
            if len(user_message) > 50:
                title += '...'
            await self._publish(ChatTitleUpdateEvent(chat_id=chat.id, title=title))
            logger.info(f'Published title update for chat {chat.id}: {title}')
            return title
        return None

    async def _extract_travel_context(
            self, chat_id: int, tool_results: List[Dict[str, Any]]) -> None:
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
            self,
            user_id: int,
            chat_id: int,
            message: str) -> AgentChatResponse:
        start_time = time.time()
        chat = await self.chat_service.get_chat(chat_id, user_id)
        if not chat:
            raise ValueError(f'Chat {chat_id} not found for user {user_id}')
        await self._publish(AgentProcessingStartedEvent(chat_id=chat_id, user_id=user_id, message=message))
        await self.chat_service.add_message(chat_id=chat_id, role=MessageRole.USER, content=message)
        await self._publish(MessageSavedEvent(chat_id=chat_id, role=MessageRole.USER.value, content=message))
        new_title = await self._maybe_generate_title(chat, message)
        context = await self._load_context(user_id, chat)
        logger.debug(
            f"Processing message for chat {chat_id}, context: {
                context.get('chat')}")
        agent = self._get_agent(chat_id)
        response = await agent.ainvoke(message=message, context=context)
        reply = response['reply']
        history = response['history']
        tool_results: List[Dict[str, Any]] = []
        generated_plan: Optional[Dict[str, Any]] = None
        for msg in history:
            if isinstance(msg, ToolMessage):
                content = msg.content
                result_data = content
                if isinstance(content, str):
                    try:
                        result_data = json.loads(content)
                    except json.JSONDecodeError:
                        pass
                tool_results.append({'name': msg.name, 'result': result_data})
                await self._publish(ToolExecutedEvent(chat_id=chat_id, tool_name=msg.name or 'unknown', tool_input='', tool_output=content if isinstance(content, str) else json.dumps(result_data), execution_time_ms=0))
                if msg.name == 'logistics_optimizer' and isinstance(
                        result_data, dict):
                    generated_plan = result_data
        if isinstance(reply, str) and reply:
            await self.chat_service.add_message(chat_id=chat_id, role=MessageRole.ASSISTANT, content=reply)
            await self._publish(MessageSavedEvent(chat_id=chat_id, role=MessageRole.ASSISTANT.value, content=reply))
        await self._extract_travel_context(chat_id, tool_results)
        if generated_plan:
            await self._publish(TravelPlanGeneratedEvent(chat_id=chat_id, user_id=user_id, plan_data=json.dumps(generated_plan)))
        processing_time_ms = int((time.time() - start_time) * 1000)
        await self._publish(AgentProcessingCompletedEvent(chat_id=chat_id, user_id=user_id, reply=reply, tool_calls=json.dumps([t['name'] for t in tool_results]) if tool_results else None))
        logger.info(
            f'Agent processed message for chat {chat_id} in {processing_time_ms}ms')
        metadata = {'tool_results': tool_results}
        if generated_plan:
            metadata['generated_plan'] = generated_plan
        return AgentChatResponse(
            reply=reply,
            chat_id=chat_id,
            metadata=metadata)

    async def create_chat_and_process(
            self, user_id: int, message: str) -> tuple[Chat, AgentChatResponse]:
        chat = await self.chat_service.create_chat(user_id)
        response = await self.process_message(user_id, chat.id, message)
        return (chat, response)
