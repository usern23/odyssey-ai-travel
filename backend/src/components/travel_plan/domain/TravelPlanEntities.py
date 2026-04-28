from __future__ import annotations
import enum
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Tuple


# ── Daily schedule constraints ────────────────────────────────────────
# Hard window for every day: nothing is scheduled outside this range.
DAY_WINDOW_START = time(10, 0)
DAY_WINDOW_END = time(22, 0)

# Minute granularity for activity start/end times in the public schedule.
TIME_ROUND_MINUTES = 5


def _round_up_to_step(t: time, step_minutes: int = TIME_ROUND_MINUTES) -> time:
    """Round a ``time`` value up to the next multiple of ``step_minutes``."""
    total = t.hour * 60 + t.minute
    remainder = total % step_minutes
    if remainder:
        total += step_minutes - remainder
    # Extra minute rollover is not expected in plans, but stay safe.
    total = min(total, 23 * 60 + 59)
    return time(total // 60, total % 60)


# Fallback opening hours per category when the POI itself does not expose them.
# ``None`` endpoints mean "use DAY_WINDOW_*".
_CATEGORY_DEFAULT_HOURS: Dict[str, Tuple[time, time]] = {
    'museum':        (time(10, 0), time(18, 0)),
    'landmark':      (time(0, 0),  time(23, 59)),
    'restaurant':    (time(12, 0), time(23, 0)),
    'cafe':          (time(9, 0),  time(22, 0)),
    'park':          (time(0, 0),  time(23, 59)),
    'beach':         (time(0, 0),  time(23, 59)),
    'shopping':      (time(10, 0), time(22, 0)),
    'entertainment': (time(10, 0), time(22, 0)),
    'nightlife':     (time(20, 0), time(23, 59)),
    'religious':     (time(8, 0),  time(20, 0)),
    'nature':        (time(0, 0),  time(23, 59)),
    'viewpoint':     (time(0, 0),  time(23, 59)),
    'hotel':         (time(0, 0),  time(23, 59)),
    'transport':     (time(0, 0),  time(23, 59)),
    'other':         (time(10, 0), time(20, 0)),
}


_TIME_RE = re.compile(r'(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})')


def resolve_opening_window(
    opening_hours: Optional[str], category: str,
    day_start: Optional[time] = None, day_end: Optional[time] = None,
) -> Tuple[time, time]:
    """Derive a (open_time, close_time) pair from free-form opening_hours.

    ``day_start`` / ``day_end`` override the default ``DAY_WINDOW_*``
    when the caller wants a wider or shifted active day (e.g. user set
    ``start_hour=7``).
    """
    lo = day_start if day_start is not None else DAY_WINDOW_START
    hi = day_end if day_end is not None else DAY_WINDOW_END
    opened: Optional[Tuple[time, time]] = None
    if opening_hours:
        text = str(opening_hours).lower()
        if '24/7' in text or 'круглосуточ' in text:
            opened = (time(0, 0), time(23, 59))
        else:
            m = _TIME_RE.search(text)
            if m:
                try:
                    oh, om, ch, cm = (int(x) for x in m.groups())
                    if 0 <= oh <= 23 and 0 <= om < 60 and 0 <= ch <= 24 and 0 <= cm < 60:
                        if ch == 24 and cm == 0:
                            ch, cm = 23, 59
                        opened = (time(oh, om), time(ch, cm))
                except ValueError:
                    opened = None
    if opened is None:
        opened = _CATEGORY_DEFAULT_HOURS.get(category, (lo, hi))
    open_t, close_t = opened
    if open_t < lo:
        open_t = lo
    if close_t > hi:
        close_t = hi
    if close_t <= open_t:
        # Degenerate window → fall back to the active day window.
        return lo, hi
    return open_t, close_t


class PlaceCategory(str, enum.Enum):
    MUSEUM = 'museum'
    LANDMARK = 'landmark'
    RESTAURANT = 'restaurant'
    CAFE = 'cafe'
    PARK = 'park'
    BEACH = 'beach'
    SHOPPING = 'shopping'
    ENTERTAINMENT = 'entertainment'
    NIGHTLIFE = 'nightlife'
    RELIGIOUS = 'religious'
    NATURE = 'nature'
    VIEWPOINT = 'viewpoint'
    HOTEL = 'hotel'
    TRANSPORT = 'transport'
    OTHER = 'other'


@dataclass
class Place:
    name: str
    lat: float
    lon: float
    category: PlaceCategory = PlaceCategory.OTHER
    visit_duration_min: int = 60
    opening_hours: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    price_level: Optional[int] = None
    source: Optional[str] = None

    @property
    def coordinates(self) -> tuple[float, float]:
        return (self.lon, self.lat)

    @property
    def coordinates_lat_lon(self) -> tuple[float, float]:
        return (self.lat, self.lon)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'lat': self.lat,
            'lon': self.lon,
            'category': self.category.value,
            'visit_duration_min': self.visit_duration_min,
            'opening_hours': self.opening_hours,
            'description': self.description,
            'address': self.address,
            'rating': self.rating,
            'price_level': self.price_level,
            'source': self.source}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Place':
        category = data.get('category', 'other')
        if isinstance(category, str):
            category = PlaceCategory(category)
        return cls(
            name=data['name'],
            lat=data['lat'],
            lon=data['lon'],
            category=category,
            visit_duration_min=data.get(
                'visit_duration_min',
                60),
            opening_hours=data.get('opening_hours'),
            description=data.get('description'),
            address=data.get('address'),
            rating=data.get('rating'),
            price_level=data.get('price_level'),
            source=data.get('source'))


@dataclass
class Activity:
    place: Place
    start_time: time
    end_time: time
    travel_time_from_prev_min: int = 0
    travel_distance_from_prev_km: float = 0.0
    notes: Optional[str] = None

    @property
    def duration_min(self) -> int:
        start_minutes = self.start_time.hour * 60 + self.start_time.minute
        end_minutes = self.end_time.hour * 60 + self.end_time.minute
        return end_minutes - start_minutes

    def to_dict(self) -> Dict[str, Any]:
        return {
            'place': self.place.to_dict(),
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'travel_time_from_prev_min': self.travel_time_from_prev_min,
            'travel_distance_from_prev_km': self.travel_distance_from_prev_km,
            'notes': self.notes}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Activity':
        return cls(
            place=Place.from_dict(
                data['place']), start_time=time.fromisoformat(
                data['start_time']), end_time=time.fromisoformat(
                data['end_time']), travel_time_from_prev_min=data.get(
                    'travel_time_from_prev_min', 0), travel_distance_from_prev_km=data.get(
                        'travel_distance_from_prev_km', 0.0), notes=data.get('notes'))


@dataclass
class DayPlan:
    day_number: int
    date: date
    activities: List[Activity] = field(default_factory=list)
    route_geometry: Optional[str] = None
    total_distance_km: float = 0.0
    total_travel_time_min: int = 0
    total_visit_time_min: int = 0

    @property
    def start_time(self) -> Optional[time]:
        return self.activities[0].start_time if self.activities else None

    @property
    def end_time(self) -> Optional[time]:
        return self.activities[-1].end_time if self.activities else None

    @property
    def places_count(self) -> int:
        return len(self.activities)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'day_number': self.day_number,
            'date': self.date.isoformat(),
            'activities': [
                a.to_dict() for a in self.activities],
            'route_geometry': self.route_geometry,
            'total_distance_km': self.total_distance_km,
            'total_travel_time_min': self.total_travel_time_min,
            'total_visit_time_min': self.total_visit_time_min}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DayPlan':
        return cls(
            day_number=data['day_number'], date=date.fromisoformat(
                data['date']), activities=[
                Activity.from_dict(a) for a in data.get(
                    'activities', [])], route_geometry=data.get('route_geometry'), total_distance_km=data.get(
                    'total_distance_km', 0.0), total_travel_time_min=data.get(
                        'total_travel_time_min', 0), total_visit_time_min=data.get(
                            'total_visit_time_min', 0))

    def to_markdown(self) -> str:
        """Render a single day as Markdown.

        Mirrors the per-day section of ``TravelPlan.to_markdown`` so that
        ``replan_day`` and any single-day endpoint can return a coherent
        snippet without rebuilding the whole plan.
        """
        lines: List[str] = [f'## День {self.day_number} ({self.date})', '']
        if not self.activities:
            lines.append('_Активности на этот день не запланированы._')
            lines.append('')
            return '\n'.join(lines)
        for i, activity in enumerate(self.activities, 1):
            place = activity.place
            time_str = (
                f"{activity.start_time.strftime('%H:%M')}"
                f"–{activity.end_time.strftime('%H:%M')}"
            )
            travel_info = (
                f'🚶 {activity.travel_time_from_prev_min} мин'
                if activity.travel_time_from_prev_min > 0 else ''
            )
            source_tag = ''
            if getattr(place, 'source', None):
                label = {'2gis': '2GIS', 'overpass': 'OSM',
                         'llm': 'LLM', 'google': 'Google'}.get(
                    place.source, place.source,
                )
                source_tag = f' · [{label}]'
            rating_tag = (
                f' ⭐ {place.rating:.1f}' if place.rating is not None else ''
            )
            lines.append(
                f'{i}. **{time_str}** — {place.name}{rating_tag} '
                f'({place.category.value}){source_tag}'
            )
            if place.opening_hours:
                lines.append(f'   🕒 {place.opening_hours}')
            if place.description:
                lines.append(f'   {place.description}')
            if travel_info:
                lines.append(f'   {travel_info}')
            lines.append('')
        lines.append(
            f'📍 Расстояние за день: {self.total_distance_km:.1f} км · '
            f'🚶 {self.total_travel_time_min} мин в пути'
        )
        lines.append('')
        return '\n'.join(lines)


@dataclass
class TravelPlan:
    destination: str
    hotel: Place
    days: List[DayPlan] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_places: int = 0
    total_distance_km: float = 0.0
    total_travel_time_min: int = 0
    quality_score: float = 0.0
    quality_report: Optional[Dict[str, Any]] = None
    # Candidate pool used during plan generation. Stored so that replanning
    # (rain/closed POIs) can re-optimise a single day without re-querying
    # external POI sources. May be empty for legacy plans.
    candidates: List[Place] = field(default_factory=list)
    # Inputs from the original generation request needed to faithfully
    # re-run the solver on a single day.
    user_preferences: Optional[Dict[str, float]] = None
    food_preferences: Optional[Dict[str, bool]] = None
    hours_per_day: float = 8.0
    start_hour: int = 10
    meal_count_per_day: int = 2
    # Structured warnings collected during plan generation. Each note is
    # ``{'type': str, 'severity': 'info'|'warn'|'error', 'message': str,
    # 'data': dict}``. Surfaced to the user via to_markdown so the agent
    # can transparently explain compromises (understaffed days, overflow,
    # weather conflicts, etc.).
    plan_notes: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        self._recalculate_stats()

    def _recalculate_stats(self) -> None:
        self.total_places = sum((day.places_count for day in self.days))
        self.total_distance_km = sum(
            (day.total_distance_km for day in self.days))
        self.total_travel_time_min = sum(
            (day.total_travel_time_min for day in self.days))
        if self.days:
            self.start_date = self.days[0].date
            self.end_date = self.days[-1].date

    @property
    def num_days(self) -> int:
        return len(self.days)

    def add_day(self, day_plan: DayPlan) -> None:
        self.days.append(day_plan)
        self._recalculate_stats()

    def get_day(self, day_number: int) -> Optional[DayPlan]:
        for day in self.days:
            if day.day_number == day_number:
                return day
        return None

    def get_all_places(self) -> List[Place]:
        places = []
        for day in self.days:
            for activity in day.activities:
                places.append(activity.place)
        return places

    def to_dict(self) -> Dict[str, Any]:
        return {
            'destination': self.destination,
            'hotel': self.hotel.to_dict(),
            'days': [
                day.to_dict() for day in self.days],
            'created_at': self.created_at.isoformat(),
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'total_places': self.total_places,
            'total_distance_km': self.total_distance_km,
            'total_travel_time_min': self.total_travel_time_min,
            'quality_score': self.quality_score,
            'quality_report': self.quality_report,
            'candidates': [c.to_dict() for c in self.candidates],
            'user_preferences': self.user_preferences,
            'food_preferences': self.food_preferences,
            'hours_per_day': self.hours_per_day,
            'start_hour': self.start_hour,
            'meal_count_per_day': self.meal_count_per_day,
            'plan_notes': list(self.plan_notes)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TravelPlan':
        plan = cls(
            destination=data['destination'],
            hotel=Place.from_dict(data['hotel']),
            days=[
                DayPlan.from_dict(d) for d in data.get('days', [])
            ],
            created_at=datetime.fromisoformat(data['created_at'])
            if data.get('created_at') else datetime.utcnow(),
            candidates=[
                Place.from_dict(c) for c in data.get('candidates', [])
            ],
            user_preferences=data.get('user_preferences'),
            food_preferences=data.get('food_preferences'),
            hours_per_day=float(data.get('hours_per_day', 8.0)),
            start_hour=int(data.get('start_hour', 10)),
            meal_count_per_day=int(data.get('meal_count_per_day', 2)),
            plan_notes=list(data.get('plan_notes') or []),
        )
        return plan

    def to_markdown(self) -> str:
        avg_km = (self.total_distance_km / len(self.days)) if self.days else 0.0
        avg_min = (self.total_travel_time_min // len(self.days)) if self.days else 0
        lines = [f'# 🗺️ План путешествия: {self.destination}',
                 f'',
                 f'**Отель:** {self.hotel.name}',
                 f'**Даты:** {self.start_date} — {self.end_date}',
                 f'**Всего мест:** {self.total_places}',
                 f'**Общее расстояние:** {self.total_distance_km:.1f} км (~{avg_km:.1f} км/день)',
                 f'**Время в пути:** {self.total_travel_time_min} мин (~{avg_min} мин/день)',
                 f'']
        # Structured warnings about compromises made during planning
        # (understaffed days, overflow, weather, etc.). Surface near the
        # top so the user sees them before the daily breakdown.
        if self.plan_notes:
            lines.append('## ⚠️ Замечания по плану')
            lines.append('')
            severity_icon = {'error': '❌', 'warn': '⚠️', 'info': 'ℹ️'}
            for note in self.plan_notes:
                icon = severity_icon.get(note.get('severity', 'info'), 'ℹ️')
                msg = note.get('message') or ''
                if msg:
                    lines.append(f'- {icon} {msg}')
            lines.append('')
        for day in self.days:
            lines.append(f'## День {day.day_number} ({day.date})')
            lines.append(f'')
            for i, activity in enumerate(day.activities, 1):
                place = activity.place
                time_str = f"{activity.start_time.strftime('%H:%M')}–{activity.end_time.strftime('%H:%M')}"
                if activity.travel_time_from_prev_min > 0:
                    travel_info = f'🚶 {activity.travel_time_from_prev_min} мин'
                else:
                    travel_info = ''
                source_tag = ''
                if place.source:
                    label = {'2gis': '2GIS', 'overpass': 'OSM', 'llm': 'LLM', 'google': 'Google'}.get(
                        place.source, place.source,
                    )
                    source_tag = f' · [{label}]'
                rating_tag = ''
                if place.rating is not None:
                    rating_tag = f' ⭐ {place.rating:.1f}'
                lines.append(
                    f'{i}. **{time_str}** — {place.name}{rating_tag} ({place.category.value}){source_tag}')
                if place.opening_hours:
                    lines.append(f'   🕒 {place.opening_hours}')
                if place.description:
                    lines.append(f'   {place.description}')
                if travel_info:
                    lines.append(f'   {travel_info}')
                lines.append('')
            lines.append(
                f'📍 Расстояние за день: {day.total_distance_km:.1f} км · 🚶 {day.total_travel_time_min} мин в пути')
            lines.append(f'')
        return '\n'.join(lines)
