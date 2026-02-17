from __future__ import annotations
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.agent.infrastructure.tools.auxiliary.web_search import WebSearchTool
from src.components.users.infrastructure.models import UserProfile


class DestinationSuggester:

    def __init__(
            self,
            db_session: AsyncSession,
            web_search_tool: Optional[WebSearchTool] = None):
        self.db_session = db_session
        self.web_search = web_search_tool or WebSearchTool(model='gpt-4.1')

    async def suggest(self,
                      user_id: int,
                      interests: Optional[List[str]] = None,
                      budget: Optional[str] = None,
                      season: Optional[str] = None,
                      region: Optional[str] = None,
                      limit: int = 5) -> Dict[str,
                                              Any]:
        profile = await self._load_profile(user_id)
        criteria = self._build_criteria(
            profile, interests, budget, season, region)
        query = self._build_search_query(criteria, limit)
        search_result = await self.web_search.search(query=query, system_prompt='Ты эксперт по путешествиям. Предложи направления для путешествия. Для каждого направления укажи: город, страну, краткое описание (2-3 предложения), и для чего подходит (пляж, культура, природа и т.д.). Отвечай на русском языке.')
        if not search_result.get('success'):
            return {
                'success': False,
                'error': search_result.get(
                    'error',
                    'Search failed'),
                'destinations': [],
                'search_criteria': criteria}
        return {
            'success': True,
            'destinations_info': search_result.get(
                'content',
                ''),
            'citations': search_result.get(
                'citations',
                []),
            'search_criteria': criteria,
            'hint': 'Спросите пользователя, какое направление его заинтересовало, затем используйте suggest_flights для поиска билетов.'}

    def _build_criteria(self,
                        profile: Optional[UserProfile],
                        interests: Optional[List[str]],
                        budget: Optional[str],
                        season: Optional[str],
                        region: Optional[str]) -> Dict[str,
                                                       Any]:
        criteria = {}
        if interests:
            criteria['interests'] = interests
        elif profile and profile.primary_interests:
            criteria['interests'] = profile.primary_interests
        if budget:
            criteria['budget'] = budget
        elif profile and profile.budget_preference:
            criteria['budget'] = profile.budget_preference.value
        if season:
            criteria['season'] = season
        if region:
            criteria['region'] = region
        if profile and profile.travel_style:
            criteria['travel_style'] = profile.travel_style.value
        return criteria

    def _build_search_query(self, criteria: Dict[str, Any], limit: int) -> str:
        parts = [f'Топ {limit} направлений для путешествия']
        if criteria.get('season'):
            parts.append(f"на {criteria['season']}")
        if criteria.get('region'):
            parts.append(f"в {criteria['region']}")
        if criteria.get('interests'):
            interests_str = ', '.join(criteria['interests'][:3])
            parts.append(f'для любителей: {interests_str}')
        if criteria.get('budget'):
            budget_map = {
                'budget': 'бюджетный отдых',
                'mid_range': 'средний бюджет',
                'luxury': 'люкс отдых'}
            parts.append(budget_map.get(criteria['budget'], ''))
        if criteria.get('travel_style'):
            style_map = {
                'relaxed': 'спокойный отдых',
                'fast_paced': 'активный отдых',
                'balanced': 'сбалансированный отдых'}
            parts.append(style_map.get(criteria['travel_style'], ''))
        return ' '.join(parts)

    async def _load_profile(self, user_id: int) -> Optional[UserProfile]:
        result = await self.db_session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        return result.scalar_one_or_none()
