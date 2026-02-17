from __future__ import annotations
import enum
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional


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
            'price_level': self.price_level}

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
            price_level=data.get('price_level'))


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
            'total_travel_time_min': self.total_travel_time_min}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TravelPlan':
        plan = cls(
            destination=data['destination'], hotel=Place.from_dict(
                data['hotel']), days=[
                DayPlan.from_dict(d) for d in data.get(
                    'days', [])], created_at=datetime.fromisoformat(
                    data['created_at']) if data.get('created_at') else datetime.utcnow())
        return plan

    def to_markdown(self) -> str:
        lines = [f'# 🗺️ План путешествия: {self.destination}',
                 f'',
                 f'**Отель:** {self.hotel.name}',
                 f'**Даты:** {self.start_date} — {self.end_date}',
                 f'**Всего мест:** {self.total_places}',
                 f'**Общее расстояние:** {self.total_distance_km:.1f} км',
                 f'**Время в пути:** {self.total_travel_time_min} мин',
                 f'']
        for day in self.days:
            lines.append(f'## День {day.day_number} ({day.date})')
            lines.append(f'')
            for i, activity in enumerate(day.activities, 1):
                place = activity.place
                time_str = f"{
                    activity.start_time.strftime('%H:%M')}–{
                    activity.end_time.strftime('%H:%M')}"
                if activity.travel_time_from_prev_min > 0:
                    travel_info = f'🚶 {activity.travel_time_from_prev_min} мин'
                else:
                    travel_info = ''
                lines.append(
                    f'{i}. **{time_str}** — {place.name} ({place.category.value})')
                if place.description:
                    lines.append(f'   {place.description}')
                if travel_info:
                    lines.append(f'   {travel_info}')
                lines.append('')
            lines.append(
                f'📍 Расстояние за день: {
                    day.total_distance_km:.1f} км')
            lines.append(f'')
        return '\n'.join(lines)
