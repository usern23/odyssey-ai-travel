"""YouTubeSearchTool — поиск видео по направлению поездки.

Использует YouTube Data API v3 (`search.list`). Ключ читается из
`settings.youtube_api_key`. Если ключ не задан, инструмент возвращает
понятную ошибку, не падает.

Особенности:
- Запросы кэшируются in-memory на 6 часов (квота YouTube Data API — 10k
  единиц/день, один search ≈ 100 единиц).
- Возвращает компактный список словарей с url, title, channel, published_at.
- НЕ обращается к LLM: чисто HTTP-клиент.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from src.common.configs.settings import settings

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 6 * 3600
DEFAULT_MAX_RESULTS = 5
HARD_MAX_RESULTS = 10


class YouTubeSearchTool:
    """Async client for YouTube Data API v3 `search.list`."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or settings.youtube_api_key
        self._base_url = base_url or settings.youtube_base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _cache_key(query: str, max_results: int, language: Optional[str]) -> str:
        return f'{query.strip().lower()}|{max_results}|{(language or "").lower()}'

    async def search_videos(
        self,
        query: str,
        max_results: int = DEFAULT_MAX_RESULTS,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search YouTube videos. Returns ``{'success', 'videos', 'error'}``."""
        if not self._api_key:
            return {
                'success': False,
                'error': 'YouTube API key is not configured',
                'videos': [],
            }
        if not query or not query.strip():
            return {
                'success': False,
                'error': 'Empty query',
                'videos': [],
            }

        max_results = max(1, min(int(max_results or DEFAULT_MAX_RESULTS), HARD_MAX_RESULTS))
        ck = self._cache_key(query, max_results, language)

        async with self._lock:
            cached = self._cache.get(ck)
            if cached and (time.monotonic() - cached[0]) < CACHE_TTL_SECONDS:
                logger.info('youtube_search cache hit: %s', query[:60])
                return {'success': True, 'videos': cached[1], 'cached': True}

        params: Dict[str, Any] = {
            'part': 'snippet',
            'q': query,
            'type': 'video',
            'maxResults': max_results,
            'safeSearch': 'moderate',
            'key': self._api_key,
        }
        if language:
            params['relevanceLanguage'] = language

        try:
            client = await self._get_client()
            r = await client.get(f'{self._base_url}/search', params=params)
        except httpx.RequestError as exc:
            logger.warning('YouTube search network error: %s', exc)
            return {
                'success': False,
                'error': f'Network error: {exc}',
                'videos': [],
            }

        if r.status_code != 200:
            logger.warning(
                'YouTube search HTTP %s: %s', r.status_code, r.text[:200])
            return {
                'success': False,
                'error': f'HTTP {r.status_code}: {r.text[:200]}',
                'videos': [],
            }

        try:
            data = r.json()
        except ValueError:
            return {'success': False, 'error': 'Invalid JSON', 'videos': []}

        videos: List[Dict[str, Any]] = []
        for item in data.get('items', []):
            video_id = (item.get('id') or {}).get('videoId')
            snippet = item.get('snippet') or {}
            if not video_id:
                continue
            videos.append({
                'video_id': video_id,
                'url': f'https://www.youtube.com/watch?v={video_id}',
                'title': snippet.get('title'),
                'description': snippet.get('description'),
                'channel': snippet.get('channelTitle'),
                'published_at': snippet.get('publishedAt'),
                'thumbnail': (
                    (snippet.get('thumbnails') or {}).get('medium')
                    or (snippet.get('thumbnails') or {}).get('default')
                    or {}
                ).get('url'),
            })

        async with self._lock:
            self._cache[ck] = (time.monotonic(), videos)

        return {'success': True, 'videos': videos, 'cached': False}
