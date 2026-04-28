"""WeatherImpactTool — converts weather forecasts into planning penalties.

The tool is pluggable: when ``OPENWEATHER_API_KEY`` is not configured (which is
the current state of the project) the :class:`StubWeatherProvider` is used and
returns neutral weather, so calling code does not need to special-case the
"no key" scenario.  When the key is available the :class:`OpenWeatherProvider`
kicks in automatically.

The public API exposed to the planner/replanner is :func:`compute_category_modifiers`
which returns a mapping ``{category: multiplier}`` applied to POI utility
scores.  For example, heavy rain roughly halves the attractiveness of outdoor
landmarks while slightly boosting museums and galleries.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx

from src.common.configs.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class WeatherCondition:
    """Aggregated weather state for a specific day.

    Values are intentionally coarse: we only need rough signals (rainy, hot,
    cold, sunny) to bias the planner, not a precise forecast.
    """

    date: date
    # Broad condition code: 'clear', 'clouds', 'rain', 'snow', 'thunderstorm',
    # 'fog', 'extreme'. Maps from OpenWeather `weather[0].main`.
    condition: str = 'clear'
    temp_c: Optional[float] = None  # daytime temperature in °C
    precipitation_mm: float = 0.0
    wind_speed_ms: Optional[float] = None
    description: str = ''

    @property
    def is_rainy(self) -> bool:
        return self.condition in {'rain', 'drizzle', 'thunderstorm'} or self.precipitation_mm >= 2.0

    @property
    def is_snowy(self) -> bool:
        return self.condition == 'snow'

    @property
    def is_extreme_heat(self) -> bool:
        return self.temp_c is not None and self.temp_c >= 32.0

    @property
    def is_extreme_cold(self) -> bool:
        return self.temp_c is not None and self.temp_c <= -10.0

    @property
    def is_clear(self) -> bool:
        return self.condition == 'clear' and not self.is_extreme_heat and not self.is_extreme_cold


# Category taxonomy used by OverpassClient and 2GIS aggregation.
# Separates POIs that suffer from bad weather from those that benefit.
_OUTDOOR_CATEGORIES = frozenset({'park', 'viewpoint', 'landmark', 'nature', 'beach', 'religious'})
_INDOOR_CATEGORIES = frozenset({'museum', 'entertainment', 'restaurant', 'cafe', 'shopping'})


class WeatherProvider(ABC):
    """Strategy interface for loading weather forecasts."""

    @abstractmethod
    async def get_forecast(
        self,
        lat: float,
        lon: float,
        start: date,
        days: int,
    ) -> List[WeatherCondition]:
        """Return a per-day forecast starting at `start` for `days` days."""


class StubWeatherProvider(WeatherProvider):
    """Fallback provider that returns neutral (clear) weather for every day.

    Used when no API key is configured. Keeps downstream logic uniform so
    modifier computation is always a no-op (all multipliers = 1.0).
    """

    async def get_forecast(
        self,
        lat: float,
        lon: float,
        start: date,
        days: int,
    ) -> List[WeatherCondition]:
        return [
            WeatherCondition(date=start + timedelta(days=i), condition='clear')
            for i in range(days)
        ]


class OpenWeatherProvider(WeatherProvider):
    """OpenWeatherMap 5-day / 3-hour forecast aggregated per day.

    OpenWeather's free tier gives 3-hourly forecasts for 5 days ahead. We
    aggregate them into a single :class:`WeatherCondition` per day, picking
    the worst condition and the mean daytime temperature.
    """

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self._api_key = api_key
        self._base_url = (base_url or settings.openweather_base_url).rstrip('/')
        self._timeout = timeout

    async def get_forecast(
        self,
        lat: float,
        lon: float,
        start: date,
        days: int,
    ) -> List[WeatherCondition]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f'{self._base_url}/forecast',
                    params={
                        'lat': lat,
                        'lon': lon,
                        'appid': self._api_key,
                        'units': 'metric',
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning('OpenWeather request failed (%s) — falling back to stub', exc)
            return await StubWeatherProvider().get_forecast(lat, lon, start, days)

        entries = payload.get('list') or []
        # Group 3-hour entries by date.
        buckets: Dict[date, List[dict]] = {}
        for item in entries:
            ts = item.get('dt')
            if ts is None:
                continue
            bucket_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            buckets.setdefault(bucket_date, []).append(item)

        # Severity ordering: higher wins.
        severity = {'clear': 0, 'clouds': 1, 'mist': 1, 'fog': 1, 'drizzle': 2,
                    'rain': 3, 'snow': 3, 'thunderstorm': 4, 'extreme': 5}

        result: List[WeatherCondition] = []
        for i in range(days):
            day = start + timedelta(days=i)
            items = buckets.get(day, [])
            if not items:
                result.append(WeatherCondition(date=day, condition='clear'))
                continue
            worst_item = max(
                items,
                key=lambda it: severity.get(
                    (it.get('weather') or [{}])[0].get('main', '').lower(), 0
                ),
            )
            weather0 = (worst_item.get('weather') or [{}])[0]
            main = weather0.get('main', '').lower() or 'clear'
            description = weather0.get('description', '')
            temps = [it.get('main', {}).get('temp') for it in items if isinstance(it.get('main'), dict)]
            temps = [t for t in temps if isinstance(t, (int, float))]
            temp_c = sum(temps) / len(temps) if temps else None
            precipitation = sum(
                (it.get('rain', {}) or {}).get('3h', 0.0)
                + (it.get('snow', {}) or {}).get('3h', 0.0)
                for it in items
            )
            wind_speeds = [
                it.get('wind', {}).get('speed') for it in items if isinstance(it.get('wind'), dict)
            ]
            wind_speeds = [w for w in wind_speeds if isinstance(w, (int, float))]
            wind = max(wind_speeds) if wind_speeds else None
            result.append(
                WeatherCondition(
                    date=day,
                    condition=main,
                    temp_c=temp_c,
                    precipitation_mm=precipitation,
                    wind_speed_ms=wind,
                    description=description,
                )
            )
        return result


@dataclass
class WeatherImpactTool:
    """Compute planning modifiers based on weather."""

    provider: WeatherProvider = field(default_factory=lambda: _default_provider())

    async def get_forecast(
        self,
        lat: float,
        lon: float,
        start: date,
        days: int,
    ) -> List[WeatherCondition]:
        return await self.provider.get_forecast(lat, lon, start, days)

    @staticmethod
    def compute_category_modifiers(condition: WeatherCondition) -> Dict[str, float]:
        """Return utility multipliers for POI categories given today's weather.

        Multipliers are centred around 1.0 (neutral). Values below 1 discourage
        the planner from scheduling a category; values above 1 encourage it.
        """
        modifiers: Dict[str, float] = {}
        if condition.is_rainy:
            for cat in _OUTDOOR_CATEGORIES:
                modifiers[cat] = 0.5
            for cat in _INDOOR_CATEGORIES:
                modifiers[cat] = 1.2
        elif condition.is_snowy:
            for cat in _OUTDOOR_CATEGORIES:
                modifiers[cat] = 0.6
            for cat in _INDOOR_CATEGORIES:
                modifiers[cat] = 1.15
        elif condition.is_extreme_heat:
            for cat in _OUTDOOR_CATEGORIES:
                modifiers[cat] = 0.8
            # Indoor AC becomes more attractive during heatwaves.
            for cat in _INDOOR_CATEGORIES:
                modifiers[cat] = 1.1
        elif condition.is_extreme_cold:
            for cat in _OUTDOOR_CATEGORIES:
                modifiers[cat] = 0.7
            for cat in _INDOOR_CATEGORIES:
                modifiers[cat] = 1.1
        elif condition.is_clear:
            # Slight boost for outdoor activities on nice days.
            for cat in _OUTDOOR_CATEGORIES:
                modifiers[cat] = 1.1
        # Unknown / cloudy → neutral (no entries → multiplier defaults to 1.0).
        return modifiers


def _default_provider() -> WeatherProvider:
    """Pick a provider based on available credentials."""
    api_key = settings.openweather_api_key
    if api_key:
        return OpenWeatherProvider(api_key=api_key)
    return StubWeatherProvider()
