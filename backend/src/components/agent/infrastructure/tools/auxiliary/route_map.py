"""
Инструмент визуализации маршрута на интерактивной карте (Folium / Leaflet.js).

Генерирует HTML-файл с маркерами мест, полилиниями маршрутов по дням
и всплывающими подсказками с информацией о каждом месте.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import folium
from folium import plugins

from src.components.travel_plan.domain.entities import TravelPlan

logger = logging.getLogger(__name__)

# Цвета маршрутов для каждого дня (до 10 дней)
DAY_COLORS = [
    '#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4',
    '#42d4f4', '#f032e6', '#bfef45', '#fabed4', '#469990',
]

# Иконки по категориям мест
CATEGORY_ICONS = {
    'museum': 'university',
    'landmark': 'monument',
    'park': 'tree',
    'restaurant': 'utensils',
    'cafe': 'coffee',
    'religious': 'place-of-worship',
    'entertainment': 'masks-theater',
    'shopping': 'bag-shopping',
    'nature': 'leaf',
    'viewpoint': 'binoculars',
    'beach': 'umbrella-beach',
    'hotel': 'bed',
    'transport': 'bus',
    'nightlife': 'champagne-glasses',
    'other': 'location-dot',
}


def generate_route_map(plan: TravelPlan) -> str:
    """
    Генерирует HTML-строку интерактивной карты маршрута на основе TravelPlan.

    Args:
        plan: объект TravelPlan с днями, активностями и отелем.

    Returns:
        HTML-строка с картой Leaflet.js (Folium).
    """
    hotel = plan.hotel
    center_lat = hotel.lat
    center_lon = hotel.lon

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles='OpenStreetMap',
    )

    # Маркер отеля
    folium.Marker(
        location=[hotel.lat, hotel.lon],
        popup=folium.Popup(f'<b>🏨 {hotel.name}</b><br>Отель', max_width=250),
        tooltip=hotel.name,
        icon=folium.Icon(color='red', icon='bed', prefix='fa'),
    ).add_to(m)

    all_coords = [(hotel.lat, hotel.lon)]

    for day in plan.days:
        if not day.activities:
            continue

        color = DAY_COLORS[(day.day_number - 1) % len(DAY_COLORS)]

        # Создаём FeatureGroup для дня (с возможностью показать/скрыть)
        day_group = folium.FeatureGroup(name=f'День {day.day_number} ({day.date})')

        # Маршрут: отель → места → отель
        route_coords = [(hotel.lat, hotel.lon)]

        for i, activity in enumerate(day.activities, 1):
            place = activity.place
            route_coords.append((place.lat, place.lon))
            all_coords.append((place.lat, place.lon))

            # Формируем popup с информацией
            popup_html = (
                f'<b>{i}. {place.name}</b><br>'
                f'📁 {place.category.value}<br>'
                f'⏰ {activity.start_time.strftime("%H:%M")}–{activity.end_time.strftime("%H:%M")}<br>'
                f'⏱ {place.visit_duration_min} мин'
            )
            if place.rating is not None:
                popup_html += f'<br>⭐ {place.rating:.1f}'
            if place.description:
                popup_html += f'<br><i>{place.description[:100]}</i>'

            icon_name = CATEGORY_ICONS.get(place.category.value, 'location-dot')

            folium.Marker(
                location=[place.lat, place.lon],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f'День {day.day_number}: {place.name}',
                icon=folium.Icon(color='blue', icon=icon_name, prefix='fa'),
            ).add_to(day_group)

            # Номер порядка
            folium.Marker(
                location=[place.lat, place.lon],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:10px;color:white;background:{color};'
                         f'border-radius:50%;width:18px;height:18px;text-align:center;'
                         f'line-height:18px;font-weight:bold;border:1px solid white;">{i}</div>',
                    icon_size=(18, 18),
                    icon_anchor=(9, 9),
                ),
            ).add_to(day_group)

        # Возврат в отель
        route_coords.append((hotel.lat, hotel.lon))

        # Если есть geometry от ORS, используем его
        if day.route_geometry:
            try:
                geom = json.loads(day.route_geometry)
                if geom.get('type') == 'LineString' and geom.get('coordinates'):
                    # GeoJSON coordinates — [lon, lat], Folium needs [lat, lon]
                    ors_coords = [
                        (coord[1], coord[0])
                        for coord in geom['coordinates']
                    ]
                    folium.PolyLine(
                        locations=ors_coords,
                        weight=4,
                        color=color,
                        opacity=0.8,
                        tooltip=f'День {day.day_number}: {day.total_distance_km:.1f} км',
                    ).add_to(day_group)
                else:
                    _add_simple_polyline(day_group, route_coords, color, day)
            except (json.JSONDecodeError, KeyError):
                _add_simple_polyline(day_group, route_coords, color, day)
        else:
            _add_simple_polyline(day_group, route_coords, color, day)

        day_group.add_to(m)

    # Layer control для включения/выключения дней
    folium.LayerControl(collapsed=False).add_to(m)

    # Автоподгонка карты для показа всех точек
    if all_coords:
        m.fit_bounds(all_coords)

    return m._repr_html_()


def _add_simple_polyline(
    group: folium.FeatureGroup,
    coords: list,
    color: str,
    day,
) -> None:
    """Добавляет прямолинейный маршрут между точками (fallback без ORS geometry)."""
    folium.PolyLine(
        locations=coords,
        weight=4,
        color=color,
        opacity=0.8,
        dash_array='10',
        tooltip=f'День {day.day_number}: {day.total_distance_km:.1f} км',
    ).add_to(group)
