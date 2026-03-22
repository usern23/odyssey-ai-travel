from __future__ import annotations
from typing import Any, Awaitable, Callable, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.agent.infrastructure.tools.auxiliary.aviasales import AviasalesTool
from src.components.agent.infrastructure.tools.auxiliary.amadeus import AmadeusClient, get_amadeus_client
from src.components.agent.infrastructure.tools.strategic.destination_suggester import DestinationSuggester
from src.components.agent.infrastructure.tools.strategic.trip_data_collector import TripDataCollector
from src.components.agent.infrastructure.tools.strategic.travel_planner import TravelPlannerTool
from src.components.agent.infrastructure.tools.strategic.langchain_tools import create_travel_plan_tools
from src.components.agent.infrastructure.tools.langchain_adapters import DestinationSuggesterLangTool, SuggestFlightsLangTool, TripDataCollectorLangTool, WebSearchLangTool, SearchPlacesLangTool
from src.components.travel_plan.infrastructure.ors_client import ORSClient
from src.components.agent.infrastructure.tools.auxiliary.web_search import WebSearchTool


class ToolsManager:

    def __init__(self, db_session: AsyncSession,
                 chat_id: Optional[int] = None):
        self.db_session = db_session
        self.chat_id = chat_id or 0
        self._aviasales = AviasalesTool()
        self._amadeus = get_amadeus_client()
        self._ors_client = ORSClient()
        self._travel_planner = TravelPlannerTool(
            ors_client=self._ors_client, db_session=db_session)
        self._web_search = WebSearchTool(model='gpt-4.1')
        self._destination_suggester = DestinationSuggester(
            db_session=db_session, web_search_tool=self._web_search)
        self._trip_data_collector = TripDataCollector()
        self._registry: Dict[str,
                             Callable[...,
                                      Awaitable[Any]]] = {'destination_suggester.suggest': self._destination_suggester.suggest,
                                                          'suggest_flights.search': self._aviasales.get_cheapest_flight,
                                                          'trip_data_collector.collect': self._trip_data_collector.collect_and_validate,
                                                          'aviasales.get_cheapest_flight': self._aviasales.get_cheapest_flight,
                                                          'travel_planner.generate_plan': self._travel_planner.generate_travel_plan,
                                                          'travel_planner.add_place': self._travel_planner.add_place_to_plan,
                                                          'travel_planner.remove_place': self._travel_planner.remove_place_from_plan,
                                                          'travel_planner.get_plan': self._travel_planner.get_current_plan,
                                                          'travel_planner.geocode': self._travel_planner.geocode_address}

    async def execute_tool(self, tool_name: str,
                           arguments: Dict[str, Any]) -> Any:
        handler = self._registry.get(tool_name)
        if handler is None:
            available = ', '.join(sorted(self._registry))
            raise ValueError(
                f"Unknown tool '{tool_name}'. Available tools: {available}")
        return await handler(**arguments)

    def get_langchain_tools(self) -> List[Any]:
        base_tools = [
            DestinationSuggesterLangTool(
                self._destination_suggester), SuggestFlightsLangTool(
                aviasales_tool=self._aviasales, amadeus_client=self._amadeus), TripDataCollectorLangTool(
                self._trip_data_collector), WebSearchLangTool(
                    self._web_search), SearchPlacesLangTool(
                        self._web_search)]
        travel_tools = create_travel_plan_tools(
            travel_planner=self._travel_planner, chat_id=self.chat_id)
        return base_tools + travel_tools
