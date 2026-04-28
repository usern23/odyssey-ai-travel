from __future__ import annotations
import asyncio
import logging
import re
from typing import Annotated, Any, AsyncIterator, Dict, List, TypedDict
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from src.common.configs import settings
from src.components.agent.domain.SystemPrompt import build_system_prompt
logger = logging.getLogger(__name__)

AGENT_RECURSION_FRIENDLY_MESSAGE = (
    'Не хватило итераций для полного ответа. '
    'Проверьте раздел «Мои путешествия» — возможно, план уже создан. '
    'Иначе уточните детали или разбейте запрос на несколько меньших.'
)
AGENT_TIMEOUT_FRIENDLY_MESSAGE = (
    'Обработка запроса заняла слишком много времени. '
    'Попробуйте ещё раз или переформулируйте вопрос.'
)
AGENT_TIMEOUT_SECONDS = 180.0


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_context: Dict[str, Any]


class LangGraphAgent:

    def __init__(self, tools: List[BaseTool]):
        self.tools = tools
        self.model = self._init_llm()
        self.graph = self._build_graph()

    def _init_llm(self) -> ChatOpenAI:
        if not settings.llm_api_key:
            logger.warning(
                'No LLM API key provided. LangGraph agent might fail.')
        return ChatOpenAI(
            api_key=settings.llm_api_key or 'dummy',
            base_url=settings.llm_api_base_url,
            model=settings.llm_model or 'gemini-2.5-flash-lite',
            temperature=0.3)

    def _get_latest_user_message(self, messages: List[BaseMessage]) -> str:
        for message in reversed(messages):
            if isinstance(message, HumanMessage) and isinstance(message.content, str):
                return message.content
        return ''

    def _is_existing_plan_follow_up(self, message: str) -> bool:
        text = message.lower()
        if not text:
            return False
        day_pattern = re.search(r'\bday\s*\d+\b|день\s*\d+|первый день|второй день|третий день', text)
        follow_up_keywords = (
            'подробно', 'опиши', 'расскажи', 'объясни', 'уточни', 'покажи места',
            'что за место', 'что это за место', 'почему выбрал', 'почему выбрано',
            'summary', 'summarize', 'describe', 'explain', 'restate', 'clarify',
        )
        return bool(day_pattern or any(keyword in text for keyword in follow_up_keywords))

    def _is_plan_rebuild_request(self, message: str) -> bool:
        text = message.lower()
        rebuild_keywords = (
            'перестрой', 'пересобери', 'построй заново', 'сгенерируй заново',
            'заново', 'новый план', 'другой план', 'измени маршрут', 'оптимизируй',
            'замени места', 'replace places', 'rebuild', 'regenerate', 'new itinerary',
        )
        return any(keyword in text for keyword in rebuild_keywords)

    def _is_map_request(self, message: str) -> bool:
        text = message.lower()
        return any(keyword in text for keyword in (
            'карта', 'на карте', 'маршрут на карте', 'покажи карту', 'show map',
            'route map', 'map'
        ))

    def _select_tools(self, state: AgentState) -> List[BaseTool]:
        context = state.get('user_context', {})
        trip = context.get('trip') or {}
        if not trip.get('has_plan'):
            return self.tools

        latest_user_message = self._get_latest_user_message(state.get('messages', []))
        if not latest_user_message:
            return self.tools

        if self._is_existing_plan_follow_up(latest_user_message) and not self._is_plan_rebuild_request(
            latest_user_message
        ) and not self._is_map_request(latest_user_message):
            allowed_names = {'get_current_travel_plan', 'get_travel_plan_day', 'replan_day'}
            selected_tools = [tool for tool in self.tools if tool.name in allowed_names]
            if selected_tools:
                logger.debug(
                    'Using restricted follow-up toolset: %s',
                    ', '.join(tool.name for tool in selected_tools),
                )
                return selected_tools
        return self.tools

    def _build_graph(self) -> Any:
        workflow = StateGraph(AgentState)
        workflow.add_node('agent', self._agent_node)
        workflow.add_node('tools', ToolNode(self.tools))
        workflow.set_entry_point('agent')
        workflow.add_conditional_edges(
            'agent', self._should_continue, {
                'continue': 'tools', 'end': END})
        workflow.add_edge('tools', 'agent')
        return workflow.compile()

    async def _agent_node(self, state: AgentState) -> Dict[str, Any]:
        context = state.get('user_context', {})
        system_prompt_text = build_system_prompt(context)
        selected_tools = self._select_tools(state)
        messages = [
            SystemMessage(
                content=system_prompt_text)] + state['messages']
        logger.debug('System Prompt (first 200 chars): %s', system_prompt_text[:200])
        logger.debug('Messages sent to LLM: %d', len(messages))
        response = await self.model.bind_tools(selected_tools).ainvoke(messages)
        return {'messages': [response]}

    def _should_continue(self, state: AgentState) -> str:
        last_message = state['messages'][-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return 'continue'
        return 'end'

    async def ainvoke(self, message: str,
                      context: Dict[str, Any]) -> Dict[str, Any]:
        history = context.get('recent_messages', [])
        human_msg = HumanMessage(content=message)
        initial_state: AgentState = {
            'messages': history + [human_msg], 'user_context': context}
        invoke_config = {
            'recursion_limit': max(4, settings.agent_recursion_limit)}
        try:
            final_state = await asyncio.wait_for(
                self.graph.ainvoke(initial_state, config=invoke_config),
                timeout=AGENT_TIMEOUT_SECONDS,
            )
        except GraphRecursionError:
            logger.warning('Agent hit recursion limit on message: %s', message[:120])
            fallback = AIMessage(content=AGENT_RECURSION_FRIENDLY_MESSAGE)
            return {
                'reply': AGENT_RECURSION_FRIENDLY_MESSAGE,
                'history': history + [human_msg, fallback],
            }
        except asyncio.TimeoutError:
            logger.warning('Agent timed out after %.0fs on message: %s', AGENT_TIMEOUT_SECONDS, message[:120])
            fallback = AIMessage(content=AGENT_TIMEOUT_FRIENDLY_MESSAGE)
            return {
                'reply': AGENT_TIMEOUT_FRIENDLY_MESSAGE,
                'history': history + [human_msg, fallback],
            }
        last_msg = final_state['messages'][-1]
        content = last_msg.content
        return {'reply': content, 'history': final_state['messages']}

    async def astream(self, message: str,
                      context: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        """Stream agent response. Yields dicts with 'type' and 'content' keys.
        Types: 'token' (text chunk), 'tool_start', 'tool_end', 'done'."""
        history = context.get('recent_messages', [])
        initial_state: AgentState = {
            'messages': history + [HumanMessage(content=message)],
            'user_context': context}
        full_reply = ''
        invoke_config = {
            'recursion_limit': max(4, settings.agent_recursion_limit)}

        async def _event_iter() -> AsyncIterator[Dict[str, Any]]:
            async for ev in self.graph.astream_events(
                initial_state, version='v2', config=invoke_config
            ):
                yield ev

        iterator = _event_iter()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(iterator.__anext__(), timeout=AGENT_TIMEOUT_SECONDS)
                except StopAsyncIteration:
                    break
                kind = event.get('event', '')
                if kind == 'on_chat_model_stream':
                    chunk = event.get('data', {}).get('chunk')
                    if isinstance(chunk, AIMessageChunk) and chunk.content:
                        full_reply += chunk.content
                        yield {'type': 'token', 'content': chunk.content}
                elif kind == 'on_tool_start':
                    name = event.get('name', '')
                    yield {'type': 'tool_start', 'content': name}
                elif kind == 'on_tool_end':
                    name = event.get('name', '')
                    output = event.get('data', {}).get('output', '')
                    yield {'type': 'tool_end', 'content': name, 'output': output}
        except GraphRecursionError:
            logger.warning('Agent hit recursion limit during stream: %s', message[:120])
            full_reply = AGENT_RECURSION_FRIENDLY_MESSAGE
            yield {'type': 'token', 'content': AGENT_RECURSION_FRIENDLY_MESSAGE}
        except asyncio.TimeoutError:
            logger.warning('Agent stream timed out after %.0fs: %s', AGENT_TIMEOUT_SECONDS, message[:120])
            full_reply = AGENT_TIMEOUT_FRIENDLY_MESSAGE
            yield {'type': 'token', 'content': AGENT_TIMEOUT_FRIENDLY_MESSAGE}
        yield {'type': 'done', 'content': full_reply}

    @staticmethod
    async def generate_title(user_message: str) -> str:
        """Generate a short chat title from the user's first message, like ChatGPT."""
        llm = ChatOpenAI(
            api_key=settings.llm_api_key or 'dummy',
            base_url=settings.llm_api_base_url,
            model=settings.llm_model or 'gemini-2.5-flash-lite',
            temperature=0.7,
            max_tokens=30)
        prompt = (
            'Generate a short title (3-6 words, in the same language as the user message) '
            'for a chat that starts with this message. Return ONLY the title, no quotes, '
            'no explanation.\n\n'
            f'User message: {user_message[:200]}'
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        title = response.content.strip().strip('"\'«»')
        return title[:80] if title else user_message[:50]
