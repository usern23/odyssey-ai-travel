from __future__ import annotations
import logging
from typing import Annotated, Any, AsyncIterator, Dict, List, TypedDict
from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from src.common.configs import settings
from src.components.agent.domain.prompts import build_system_prompt
logger = logging.getLogger(__name__)


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
            temperature=0.3).bind_tools(
            self.tools)

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
        messages = [
            SystemMessage(
                content=system_prompt_text)] + state['messages']
        logger.debug('System Prompt (first 200 chars): %s', system_prompt_text[:200])
        logger.debug('Messages sent to LLM: %d', len(messages))
        response = await self.model.ainvoke(messages)
        return {'messages': [response]}

    def _should_continue(self, state: AgentState) -> str:
        last_message = state['messages'][-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return 'continue'
        return 'end'

    async def ainvoke(self, message: str,
                      context: Dict[str, Any]) -> Dict[str, Any]:
        history = context.get('recent_messages', [])
        initial_state: AgentState = {
            'messages': history + [HumanMessage(content=message)], 'user_context': context}
        final_state = await self.graph.ainvoke(initial_state)
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
        async for event in self.graph.astream_events(initial_state, version='v2'):
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
        yield {'type': 'done', 'content': full_reply}

    async def generate_title(self, user_message: str) -> str:
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
