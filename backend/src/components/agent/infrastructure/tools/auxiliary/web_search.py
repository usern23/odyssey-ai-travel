from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
import httpx
from src.common.configs.settings import settings
logger = logging.getLogger(__name__)


class WebSearchTool:
    MODEL_GPT4 = 'gpt-4.1'
    MODEL_GPT4_MINI = 'gpt-4.1-mini'
    MODEL_SONAR = 'sonar'
    MODEL_SONAR_PRO = 'sonar-pro'

    def __init__(
            self,
            api_key: Optional[str] = None,
            base_url: str = 'https://api.aitunnel.ru/v1',
            model: str = MODEL_GPT4,
            search_context_size: str = 'medium'):
        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url
        self.model = model
        self.search_context_size = search_context_size
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'},
                timeout=60.0)
        return self._client

    async def search(self, query: str,
                     system_prompt: Optional[str] = None) -> Dict[str, Any]:
        if not self.api_key:
            logger.error('No API key configured for web search')
            return {
                'success': False,
                'error': 'API key not configured',
                'content': '',
                'citations': []}
        client = await self._get_client()
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': query})
        payload = {
            'model': self.model,
            'messages': messages,
            'max_tokens': 4096,
            'web_search_options': {
                'search_context_size': self.search_context_size}}
        try:
            response = await client.post('/chat/completions', json=payload)
            response.raise_for_status()
            data = response.json()
            choice = data.get('choices', [{}])[0]
            message = choice.get('message', {})
            content = message.get('content', '')
            annotations = message.get('annotations', [])
            citations = []
            for ann in annotations:
                if ann.get('type') == 'url_citation':
                    citation = ann.get('url_citation', {})
                    citations.append({'url': citation.get('url'), 'title': citation.get(
                        'title'), 'content': citation.get('content')})
            logger.info(
                f'Web search completed: {len(citations)} citations found')
            return {
                'success': True,
                'content': content,
                'citations': citations}
        except httpx.HTTPStatusError as e:
            logger.error(
                f'Web search HTTP error: {e.response.status_code} - {e.response.text}')
            return {
                'success': False,
                'error': f'HTTP {e.response.status_code}: {e.response.text}',
                'content': '',
                'citations': []}
        except Exception as e:
            logger.error(f'Web search error: {e}')
            return {
                'success': False,
                'error': str(e),
                'content': '',
                'citations': []}

    async def search_places(self,
                            city: str,
                            interests: List[str],
                            num_places: int = 50) -> Dict[str, Any]:
        # ── Try 2GIS first (real data, exact coordinates) ──
        if settings.geo_api_key:
            try:
                from src.components.agent.infrastructure.tools.auxiliary.twogis_client import TwoGisClient
                twogis = TwoGisClient()
                raw_places = await twogis.search_places(city, interests, num_places)
                if raw_places:
                    enriched = await self._enrich_places_with_llm(raw_places, city)
                    logger.info('2GIS + LLM: %d places for %s', len(enriched), city)
                    return {
                        'success': True,
                        'places': enriched,
                        'raw_content': f'2GIS: {len(enriched)} places',
                        'citations': [],
                        'source': '2gis',
                    }
            except Exception as e:
                logger.warning('2GIS search failed, falling back to LLM: %s', e)

        # ── Fallback: LLM web search ──
        interests_str = ', '.join(
            interests) if interests else 'достопримечательности'
        query = f'Найди {num_places} лучших мест для посещения в городе {city}.\nИнтересы: {interests_str}.\n\nДля КАЖДОГО места укажи:\n1. Название\n2. Координаты (широта и долгота с точностью до 4 знаков)\n3. Категория (museum/landmark/park/restaurant/cafe/religious/entertainment/shopping/nature/viewpoint/beach)\n4. Примерное время посещения в минутах\n5. Рейтинг (от 0.0 до 5.0, на основе отзывов и популярности)\n6. Уровень цен (1-5): 1=бесплатно, 2=дёшево, 3=средне, 4=дорого, 5=очень дорого\n7. Краткое описание (1-2 предложения)\n\nФормат ответа - JSON массив:\n```json\n[\n  {{"name": "Название", "lat": 59.9398, "lon": 30.3146, "category": "museum", "visit_duration_min": 180, "rating": 4.8, "price_level": 4, "description": "Описание"}}\n]\n```\n\nВажно: координаты должны быть точными, проверь их!'
        system_prompt = 'Ты - эксперт по туризму. Твоя задача - находить лучшие места для посещения с точными координатами.\nВсегда возвращай данные в JSON формате. Координаты должны быть точными (проверяй через официальные источники).\nДля каждого места обязательно укажи рейтинг (0.0-5.0) и уровень цен (1-5).\nОтвечай только JSON массивом, без дополнительного текста.'
        result = await self.search(query, system_prompt)
        if not result['success']:
            return result
        content = result['content']
        places = self._parse_places_from_response(content)
        return {
            'success': True,
            'places': places,
            'raw_content': content,
            'citations': result.get('citations', []),
            'source': 'llm',
        }

    async def _enrich_places_with_llm(
        self,
        places: List[Dict[str, Any]],
        city: str,
    ) -> List[Dict[str, Any]]:
        """Use LLM to add visit_duration_min, price_level, and description."""
        BATCH_SIZE = 40
        for batch_start in range(0, len(places), BATCH_SIZE):
            batch = places[batch_start:batch_start + BATCH_SIZE]
            try:
                await self._enrich_batch(batch, city)
            except Exception as e:
                logger.warning('LLM enrichment failed for batch %d: %s', batch_start, e)
                for p in batch:
                    p.setdefault('visit_duration_min', 60)
                    p.setdefault('price_level', 2)
                    p.setdefault('description', '')
        return places

    async def _enrich_batch(
        self, batch: List[Dict[str, Any]], city: str,
    ) -> None:
        lines = []
        for i, p in enumerate(batch):
            rubrics_str = ', '.join(p.get('rubrics', [])) or p.get('category', '')
            addr = p.get('address', '')
            lines.append(f"{i + 1}. {p['name']} ({rubrics_str}) — {addr}")

        places_text = '\n'.join(lines)

        query = (
            f'Для каждого из {len(batch)} мест в городе {city} определи:\n'
            '1. visit_duration_min — рекомендуемое время посещения в минутах\n'
            '2. price_level — уровень цен (1=бесплатно, 2=дёшево, 3=средне, 4=дорого, 5=очень дорого)\n'
            '3. description — краткое описание на русском (1-2 предложения)\n\n'
            f'Места:\n{places_text}\n\n'
            'Ответь ТОЛЬКО JSON массивом:\n'
            '[{"index": 1, "visit_duration_min": 180, "price_level": 4, "description": "..."}]'
        )
        system_prompt = (
            'Ты эксперт по туризму. Для каждого места укажи реалистичное время посещения, '
            'уровень цен и описание. Отвечай ТОЛЬКО JSON массивом.'
        )

        result = await self.search(query, system_prompt)
        if not result['success']:
            raise RuntimeError(result.get('error', 'LLM enrichment failed'))

        enrichments = self._parse_enrichments(result['content'])
        for enr in enrichments:
            idx = enr.get('index', 0) - 1
            if 0 <= idx < len(batch):
                batch[idx]['visit_duration_min'] = int(enr.get('visit_duration_min', 60))
                batch[idx]['price_level'] = int(enr.get('price_level', 2))
                batch[idx]['description'] = enr.get('description', '')

        # Fill defaults for any unenriched places
        for p in batch:
            p.setdefault('visit_duration_min', 60)
            p.setdefault('price_level', 2)
            p.setdefault('description', '')

    def _parse_enrichments(self, content: str) -> List[Dict[str, Any]]:
        import json
        import re
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', content)
            if json_match:
                json_str = json_match.group(0)
            else:
                return []
        try:
            data = json.loads(json_str)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError as e:
            logger.error('Failed to parse enrichment JSON: %s', e)
            return []

    def _parse_places_from_response(
            self, content: str) -> List[Dict[str, Any]]:
        import json
        import re
        json_match = re.search('```json\\s*([\\s\\S]*?)\\s*```', content)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search('\\[\\s*\\{[\\s\\S]*\\}\\s*\\]', content)
            if json_match:
                json_str = json_match.group(0)
            else:
                logger.warning('Could not find JSON in web search response')
                return []
        try:
            places = json.loads(json_str)
            if isinstance(places, list):
                valid_places = []
                for p in places:
                    if all((k in p for k in ['name', 'lat', 'lon'])):
                        valid_places.append(
                            {
                                'name': p.get('name'), 'lat': float(
                                    p.get('lat')), 'lon': float(
                                    p.get('lon')), 'category': p.get(
                                    'category', 'other'), 'visit_duration_min': int(
                                    p.get(
                                        'visit_duration_min', 60)),
                                'rating': float(p['rating']) if p.get('rating') is not None else None,
                                'price_level': int(p['price_level']) if p.get('price_level') is not None else None,
                                'description': p.get('description')})
                return valid_places
        except json.JSONDecodeError as e:
            logger.error(f'Failed to parse places JSON: {e}')
        return []

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
