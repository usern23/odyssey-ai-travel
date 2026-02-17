from __future__ import annotations
import logging
from typing import Annotated, Any, Dict, List, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
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
        print(f'DEBUG: System Prompt:\n{system_prompt_text}')
        print(f'DEBUG: Messages sent to LLM ({len(messages)}):')
        for m in messages:
            print(f' - {m.type}: {str(m.content)[:100]}...')
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
