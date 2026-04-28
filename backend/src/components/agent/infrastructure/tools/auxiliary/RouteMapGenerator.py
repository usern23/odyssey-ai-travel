"""
Инструмент визуализации маршрута на интерактивной карте.

Автоматически выбирает рендерер:
- 2GIS MapGL — для России, Казахстана, ОАЭ и др. стран с покрытием 2GIS
- MapLibre GL JS + OpenStreetMap — для остального мира

Генерирует HTML-страницу с:
- маркером отеля «Старт/Финиш»
- пронумерованными маркерами мест (цвет = день)
- полилиниями маршрутов по дням
- стрелками направления движения
- мультивыбором дней (чекбоксы) в сайдбаре
- статистикой по дням (мест, км, мин, коэф. detour)
"""
from __future__ import annotations

import html
import json
import logging
import math
from typing import Dict, Optional

from src.common.configs.settings import settings
from src.components.travel_plan.domain.TravelPlanEntities import TravelPlan

logger = logging.getLogger(__name__)

_map_html_cache: Dict[int, str] = {}


def store_map_html(chat_id: int, html_str: str) -> None:
    _map_html_cache[chat_id] = html_str


def get_cached_map_html(chat_id: int) -> Optional[str]:
    return _map_html_cache.get(chat_id)


def invalidate_map_cache(chat_id: int) -> None:
    """Сбросить кэш карты для чата (при регенерации плана)."""
    _map_html_cache.pop(chat_id, None)


DAY_COLORS = [
    '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
    '#EC4899', '#06B6D4', '#F97316', '#6366F1', '#14B8A6',
]

CATEGORY_LABELS = {
    'museum': 'Музей', 'landmark': 'Достопримечательность', 'restaurant': 'Ресторан',
    'cafe': 'Кафе', 'park': 'Парк', 'beach': 'Пляж', 'shopping': 'Шопинг',
    'entertainment': 'Развлечение', 'nightlife': 'Ночная жизнь', 'religious': 'Религия',
    'nature': 'Природа', 'viewpoint': 'Обзорная точка', 'hotel': 'Отель',
    'transport': 'Транспорт', 'other': 'Место',
}

CATEGORY_EMOJI = {
    'museum': '🏛️', 'landmark': '🏰', 'restaurant': '🍽️', 'cafe': '☕',
    'park': '🌳', 'beach': '🏖️', 'shopping': '🛍️', 'entertainment': '🎭',
    'nightlife': '🌙', 'religious': '⛪', 'nature': '🌿', 'viewpoint': '🔭',
    'hotel': '🏨', 'transport': '🚌', 'other': '📍',
}

_TWOGIS_REGIONS = [
    (27.0, 41.0, 180.0, 82.0),  # Россия
    (46.0, 40.0, 88.0, 56.0),   # Казахстан
    (56.0, 37.0, 74.0, 46.0),   # Узбекистан
    (69.0, 39.0, 81.0, 44.0),   # Кыргызстан
    (51.0, 22.5, 56.5, 26.5),   # ОАЭ
    (29.0, 24.0, 35.0, 32.0),   # Египет
]


def _is_twogis_region(lon: float, lat: float) -> bool:
    for min_lon, min_lat, max_lon, max_lat in _TWOGIS_REGIONS:
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            return True
    return False


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _straight_line_km(hotel_lat: float, hotel_lon: float, activities) -> float:
    if not activities:
        return 0.0
    total = 0.0
    prev_lat, prev_lon = hotel_lat, hotel_lon
    for a in activities:
        total += _haversine_km(prev_lat, prev_lon, a.place.lat, a.place.lon)
        prev_lat, prev_lon = a.place.lat, a.place.lon
    total += _haversine_km(prev_lat, prev_lon, hotel_lat, hotel_lon)
    return total


def _collect_map_data(plan: TravelPlan):
    hotel = plan.hotel
    all_lons = [hotel.lon]
    all_lats = [hotel.lat]
    days_data = []

    for day in plan.days:
        if not day.activities:
            continue
        color = DAY_COLORS[(day.day_number - 1) % len(DAY_COLORS)]
        route_coords = [[hotel.lon, hotel.lat]]
        markers = []

        for i, activity in enumerate(day.activities, 1):
            place = activity.place
            all_lons.append(place.lon)
            all_lats.append(place.lat)
            route_coords.append([place.lon, place.lat])

            cat_label = CATEGORY_LABELS.get(place.category.value, 'Место')
            cat_emoji = CATEGORY_EMOJI.get(place.category.value, '📍')
            time_str = f'{activity.start_time.strftime("%H:%M")}–{activity.end_time.strftime("%H:%M")}'
            rating_str = f' · ⭐ {place.rating:.1f}' if place.rating else ''
            name_escaped = html.escape(place.name)
            desc_escaped = html.escape((place.description or '')[:80])

            popup = (
                f'<b>День {day.day_number} · №{i}</b><br>'
                f'<b>{name_escaped}</b><br>'
                f'{cat_emoji} {cat_label}{rating_str}<br>'
                f'⏰ {time_str}<br>'
                f'⏱ {place.visit_duration_min} мин'
            )
            if activity.travel_time_from_prev_min:
                popup += f'<br>🚶 от пред.: {activity.travel_time_from_prev_min} мин'
            if desc_escaped:
                popup += f'<br><i style="color:#666">{desc_escaped}</i>'

            markers.append({
                'lon': place.lon, 'lat': place.lat,
                'num': i, 'name': name_escaped, 'popup': popup,
            })

        route_coords.append([hotel.lon, hotel.lat])

        if day.route_geometry:
            try:
                geom = json.loads(day.route_geometry)
                if geom.get('type') == 'LineString' and geom.get('coordinates'):
                    route_coords = geom['coordinates']
            except (json.JSONDecodeError, KeyError):
                pass

        straight_km = _straight_line_km(hotel.lat, hotel.lon, day.activities)
        actual_km = day.total_distance_km or 0.0
        detour_ratio = (actual_km / straight_km) if straight_km > 0.05 else None

        days_data.append({
            'day_number': day.day_number,
            'date': day.date.isoformat() if hasattr(day.date, 'isoformat') else str(day.date),
            'color': color,
            'markers': markers,
            'route_coords': route_coords,
            'activity_count': len(day.activities),
            'total_distance_km': round(actual_km, 1),
            'total_travel_time_min': int(day.total_travel_time_min or 0),
            'total_visit_time_min': int(day.total_visit_time_min or 0),
            'straight_line_km': round(straight_km, 1),
            'detour_ratio': round(detour_ratio, 2) if detour_ratio else None,
        })

    if not all_lons:
        all_lons = [hotel.lon]
        all_lats = [hotel.lat]

    min_lon = min(all_lons) - 0.005
    max_lon = max(all_lons) + 0.005
    min_lat = min(all_lats) - 0.005
    max_lat = max(all_lats) + 0.005

    return days_data, min_lon, min_lat, max_lon, max_lat


def _build_sidebar(plan: TravelPlan, days_data: list) -> str:
    total_km = sum(d['total_distance_km'] for d in days_data)
    total_min = sum(d['total_travel_time_min'] for d in days_data)
    total_places = sum(d['activity_count'] for d in days_data)

    rows = []
    for d in days_data:
        detour_html = ''
        if d['detour_ratio']:
            ratio = d['detour_ratio']
            if ratio <= 1.3:
                badge_color, badge_text = '#10B981', 'оптим.'
            elif ratio <= 1.7:
                badge_color, badge_text = '#F59E0B', 'средне'
            else:
                badge_color, badge_text = '#EF4444', 'крюк'
            detour_html = (
                f'<span class="detour-badge" style="background:{badge_color}" '
                f'title="Отношение реального пути к прямой линии. Ближе к 1.0 — оптимальнее. '
                f'Прямая: {d["straight_line_km"]} км">×{ratio} {badge_text}</span>'
            )
        rows.append(
            f'<label class="day-row" data-day="{d["day_number"]}">'
            f'<input type="checkbox" checked onchange="toggleDay({d["day_number"]}, this.checked)">'
            f'<span class="day-color" style="background:{d["color"]}"></span>'
            f'<div class="day-info">'
            f'<div class="day-title">День {d["day_number"]} · {d["date"]}</div>'
            f'<div class="day-meta">'
            f'{d["activity_count"]} мест · {d["total_distance_km"]} км · {d["total_travel_time_min"]} мин пути'
            f'{detour_html}'
            f'</div></div>'
            f'</label>'
        )

    return (
        f'<div class="sidebar" id="sidebar">'
        f'<div class="sidebar-header">'
        f'<div class="sidebar-title">🗺️ {html.escape(plan.destination)}</div>'
        f'<div class="sidebar-total">{total_places} мест · {round(total_km,1)} км · {total_min} мин пешком</div>'
        f'<div class="sidebar-actions">'
        f'<button onclick="toggleAll(true)">Все</button>'
        f'<button onclick="toggleAll(false)">Ни одного</button>'
        f'<button class="collapse-btn" onclick="toggleSidebar()" title="Свернуть">−</button>'
        f'</div></div>'
        f'<div class="sidebar-body">{"".join(rows)}</div>'
        f'</div>'
    )


_COMMON_STYLES = """
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 100%; height: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  #map { width: 100%; height: 100%; }
  .sidebar {
    position: absolute; top: 12px; left: 12px;
    background: rgba(255,255,255,.97); backdrop-filter: blur(8px);
    border-radius: 12px;
    font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,.18);
    z-index: 100; max-width: 320px; max-height: calc(100% - 24px);
    display: flex; flex-direction: column; overflow: hidden;
  }
  .sidebar.collapsed .sidebar-body { display: none; }
  .sidebar.collapsed .sidebar-total { display: none; }
  .sidebar-header {
    padding: 10px 12px; border-bottom: 1px solid rgba(0,0,0,.08);
  }
  .sidebar-title { font-weight: 700; font-size: 14px; margin-bottom: 3px; }
  .sidebar-total { font-size: 11px; color: #555; margin-bottom: 6px; }
  .sidebar-actions { display: flex; gap: 6px; align-items: center; }
  .sidebar-actions button {
    font-size: 11px; padding: 3px 8px; border-radius: 6px;
    border: 1px solid rgba(0,0,0,.12); background: #fff; cursor: pointer;
  }
  .sidebar-actions button:hover { background: #f0f0f0; }
  .collapse-btn { margin-left: auto; font-weight: 700; width: 24px; height: 22px; padding: 0; }
  .sidebar-body { overflow-y: auto; padding: 6px 8px 10px; }
  .day-row {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 6px 4px; border-radius: 6px; cursor: pointer;
  }
  .day-row:hover { background: rgba(0,0,0,.04); }
  .day-row input[type="checkbox"] { margin-top: 3px; cursor: pointer; flex-shrink: 0; }
  .day-color {
    display: inline-block; width: 12px; height: 12px; border-radius: 50%;
    margin-top: 3px; flex-shrink: 0; border: 2px solid #fff;
    box-shadow: 0 0 0 1px rgba(0,0,0,.1);
  }
  .day-info { flex: 1; min-width: 0; }
  .day-title { font-weight: 600; font-size: 12px; }
  .day-meta { font-size: 11px; color: #666; margin-top: 2px; line-height: 1.35; }
  .detour-badge {
    display: inline-block; color: #fff; border-radius: 4px;
    padding: 1px 5px; font-size: 10px; font-weight: 600; margin-left: 6px;
  }
  .hotel-label {
    position: absolute; left: 50%; top: -6px;
    transform: translate(-50%, -100%);
    background: #1E293B; color: #fff; padding: 3px 8px;
    border-radius: 10px; font-size: 11px; font-weight: 600;
    white-space: nowrap; pointer-events: none;
    box-shadow: 0 2px 8px rgba(0,0,0,.3);
  }
"""


def _render_twogis(plan: TravelPlan, days_data, bounds, sidebar_html) -> str:
    api_key = settings.geo_api_key or ''
    hotel = plan.hotel
    min_lon, min_lat, max_lon, max_lat = bounds
    center_lon = (min_lon + max_lon) / 2
    center_lat = (min_lat + max_lat) / 2

    days_json = json.dumps(days_data, ensure_ascii=False)
    hotel_name_js = json.dumps(hotel.name)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{_COMMON_STYLES}
  .popup-overlay {{ position:fixed;top:0;left:0;right:0;bottom:0;display:none;z-index:9999;pointer-events:none; }}
  .popup-card {{ position:absolute;background:#fff;border-radius:12px;padding:12px 16px;box-shadow:0 4px 20px rgba(0,0,0,.2);font-size:13px;line-height:1.5;max-width:280px;pointer-events:auto; }}
  .popup-card b {{ font-size:14px; }}
  .popup-close {{ position:absolute;top:6px;right:10px;cursor:pointer;font-size:18px;color:#999;background:none;border:none; }}
</style></head><body>
<div id="map"></div>
{sidebar_html}
<div class="popup-overlay" id="popupOverlay" onclick="closePopup()">
  <div class="popup-card" id="popupCard" onclick="event.stopPropagation()">
    <button class="popup-close" onclick="closePopup()">×</button>
    <div id="popupContent"></div>
  </div>
</div>
<script src="https://mapgl.2gis.com/api/js/v1"></script>
<script>
var DAYS = {days_json};
var HOTEL = {{ lat: {hotel.lat}, lon: {hotel.lon}, name: {hotel_name_js} }};
var map = new mapgl.Map('map', {{
    center: [{center_lon}, {center_lat}],
    zoom: 13,
    key: '{api_key}',
    lang: 'ru',
    zoomControl: 'topRight'
}});

function getViewportPadding() {{
  var sidebar = document.getElementById('sidebar');
  var width = Math.max(window.innerWidth || 0, 320);
  var sidebarVisible = sidebar && !sidebar.classList.contains('collapsed');
  var left = sidebarVisible ? Math.min(340, Math.max(24, Math.floor(width * 0.34))) : 24;
  if (width < 720) left = 24;
  return {{ top: 60, bottom: 60, left: left, right: 24 }};
}}

function fitToPlan() {{
  try {{
    map.fitBounds({{
      southWest: [{min_lon}, {min_lat}],
      northEast: [{max_lon}, {max_lat}],
      padding: getViewportPadding(),
    }});
  }} catch (e) {{
    console.warn('2GIS fitBounds failed', e);
  }}
}}

new mapgl.HtmlMarker(map, {{
    coordinates: [HOTEL.lon, HOTEL.lat],
    html: '<div style="position:relative"><div style="background:#1E293B;color:#fff;width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:22px;border:3px solid #fff;box-shadow:0 3px 10px rgba(0,0,0,.45);cursor:pointer" title="' + HOTEL.name.replace(/"/g,'&quot;') + '">🏨</div><div class="hotel-label">Старт / Финиш</div></div>',
    anchor: [21, 21]
}});

var dayObjects = {{}};

function showPopup(coords, h) {{
    var pixel = map.project(coords);
    var card = document.getElementById('popupCard');
    document.getElementById('popupContent').innerHTML = h;
    card.style.left = Math.min(pixel[0], window.innerWidth - 300) + 'px';
    card.style.top = Math.max(pixel[1] - 100, 10) + 'px';
    document.getElementById('popupOverlay').style.display = 'block';
}}
function closePopup() {{ document.getElementById('popupOverlay').style.display = 'none'; }}

function buildDay(d) {{
    var polylines = [], markers = [], arrows = [];
    polylines.push(new mapgl.Polyline(map, {{ coordinates: d.route_coords, width: 9, color: '#ffffff', zIndex: 1 }}));
    polylines.push(new mapgl.Polyline(map, {{ coordinates: d.route_coords, width: 5, color: d.color, zIndex: 2 }}));

    var coords = d.route_coords;
    var numSegs = coords.length - 1;
    var maxArrows = Math.min(12, Math.max(3, Math.floor(numSegs / 4)));
    var step = Math.max(1, Math.floor(numSegs / maxArrows));
    for (var i = step; i < numSegs; i += step) {{
        var c1 = coords[Math.max(0, i - 1)], c2 = coords[i];
        var dx = c2[0] - c1[0], dy = c2[1] - c1[1];
        if (Math.abs(dx) < 0.00005 && Math.abs(dy) < 0.00005) continue;
        var angle = Math.atan2(dy, dx) * 180 / Math.PI;
        arrows.push(new mapgl.HtmlMarker(map, {{
            coordinates: c2,
            html: '<div style="width:22px;height:22px;display:flex;align-items:center;justify-content:center;background:' + d.color + ';border:2px solid #fff;border-radius:50%;transform:rotate(' + (-angle + 90) + 'deg);box-shadow:0 1px 4px rgba(0,0,0,.35);color:#fff;font-size:13px;font-weight:700;line-height:1;pointer-events:none">▲</div>',
            anchor: [11, 11]
        }}));
    }}

    d.markers.forEach(function(m) {{
        (function(mm) {{
            var marker = new mapgl.HtmlMarker(map, {{
                coordinates: [mm.lon, mm.lat],
                html: '<div style="background:' + d.color + ';color:#fff;width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.4);cursor:pointer" title="День ' + d.day_number + ': ' + mm.name + '">' + mm.num + '</div>',
                anchor: [15, 15]
            }});
            var el = marker.getElement && marker.getElement();
            if (el) el.addEventListener('click', function() {{ showPopup([mm.lon, mm.lat], mm.popup); }});
            markers.push(marker);
        }})(m);
    }});
    dayObjects[d.day_number] = {{ polylines: polylines, markers: markers, arrows: arrows }};
}}

DAYS.forEach(buildDay);

function destroyDay(dayNum) {{
    var obj = dayObjects[dayNum];
    if (!obj) return;
    obj.polylines.forEach(function(p) {{ try {{ p.destroy(); }} catch(e) {{}} }});
    obj.markers.forEach(function(m) {{ try {{ m.destroy(); }} catch(e) {{}} }});
    obj.arrows.forEach(function(a) {{ try {{ a.destroy(); }} catch(e) {{}} }});
    delete dayObjects[dayNum];
}}

function toggleDay(dayNum, show) {{
    if (show) {{
        if (dayObjects[dayNum]) return;
        var d = DAYS.find(function(x) {{ return x.day_number === dayNum; }});
        if (d) buildDay(d);
    }} else {{
        destroyDay(dayNum);
    }}
}}

function toggleAll(show) {{
    document.querySelectorAll('.day-row input[type="checkbox"]').forEach(function(cb) {{
        var dayNum = parseInt(cb.closest('.day-row').getAttribute('data-day'));
        cb.checked = show;
        toggleDay(dayNum, show);
    }});
}}

function toggleSidebar() {{
    var sb = document.getElementById('sidebar');
    sb.classList.toggle('collapsed');
    var btn = sb.querySelector('.collapse-btn');
    btn.textContent = sb.classList.contains('collapsed') ? '+' : '−';
  setTimeout(fitToPlan, 30);
}}

window.addEventListener('resize', fitToPlan);
</script></body></html>"""


def _render_maplibre(plan: TravelPlan, days_data, bounds, sidebar_html) -> str:
    hotel = plan.hotel
    min_lon, min_lat, max_lon, max_lat = bounds
    center_lon = (min_lon + max_lon) / 2
    center_lat = (min_lat + max_lat) / 2

    days_json = json.dumps(days_data, ensure_ascii=False)
    hotel_name_js = json.dumps(hotel.name)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<style>{_COMMON_STYLES}
  .marker {{
    display:flex;align-items:center;justify-content:center;
    border-radius:50%;color:#fff;font-weight:700;
    border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.4);
    cursor:pointer;transition:transform .15s;
  }}
  .marker:hover {{ transform:scale(1.15); }}
  .marker-hotel {{ width:42px;height:42px;font-size:22px; background:#1E293B; }}
  .marker-place {{ width:30px;height:30px;font-size:14px; }}
  .hotel-wrap {{ position: relative; }}
  .maplibregl-popup-content {{
    border-radius:12px !important;padding:12px 16px !important;
    box-shadow:0 4px 20px rgba(0,0,0,.18) !important;
    font-size:13px;line-height:1.5;
  }}
  .maplibregl-popup-content b {{ font-size:14px; }}
  .maplibregl-popup-close-button {{ font-size:18px;color:#999;padding:4px 8px; }}
  .arrow-marker {{
    width:22px;height:22px;display:flex;align-items:center;justify-content:center;
    border-radius:50%; border:2px solid #fff; color:#fff;
    font-size:13px;font-weight:700; box-shadow:0 1px 4px rgba(0,0,0,.35);
    pointer-events:none;
  }}
</style></head><body>
<div id="map"></div>
{sidebar_html}
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script>
var DAYS = {days_json};
var HOTEL = {{ lat: {hotel.lat}, lon: {hotel.lon}, name: {hotel_name_js} }};
var map = new maplibregl.Map({{
  container: 'map',
  style: {{
    version: 8,
    sources: {{ osm: {{ type: 'raster', tiles: ['https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png'], tileSize: 256, attribution: '' }} }},
    layers: [{{ id: 'osm', type: 'raster', source: 'osm' }}]
  }},
  center: [{center_lon}, {center_lat}], zoom: 13
}});

function getViewportPadding() {{
  var sidebar = document.getElementById('sidebar');
  var width = Math.max(window.innerWidth || 0, 320);
  var sidebarVisible = sidebar && !sidebar.classList.contains('collapsed');
  var left = sidebarVisible ? Math.min(340, Math.max(24, Math.floor(width * 0.34))) : 24;
  if (width < 720) left = 24;
  return {{ top: 60, bottom: 60, left: left, right: 24 }};
}}

function fitToPlan() {{
  try {{
    map.fitBounds([[{min_lon},{min_lat}],[{max_lon},{max_lat}]], {{
      padding: getViewportPadding(),
      maxZoom: 14,
      duration: 0,
    }});
  }} catch (e) {{
    console.warn('MapLibre fitBounds failed', e);
  }}
}}

var viewportSyncTimer = null;
var viewportObserver = null;
var initialIdleSyncDone = false;

function syncViewport() {{
  try {{
    map.resize();
  }} catch (e) {{
    console.warn('MapLibre resize failed', e);
  }}
  fitToPlan();
}}

function scheduleViewportSync(delay) {{
  if (viewportSyncTimer) {{
    clearTimeout(viewportSyncTimer);
  }}
  viewportSyncTimer = setTimeout(function() {{
    syncViewport();
  }}, delay || 0);
}}

var dayObjects = {{}};

function buildDay(d) {{
  var markers = [], arrows = [];
  var sourceId = 'route-' + d.day_number;
  var outlineId = 'route-outline-' + d.day_number;
  var lineId = 'route-line-' + d.day_number;

  map.addSource(sourceId, {{
    type: 'geojson',
    data: {{ type: 'Feature', geometry: {{ type: 'LineString', coordinates: d.route_coords }}, properties: {{}} }}
  }});
  map.addLayer({{
    id: outlineId, type: 'line', source: sourceId,
    paint: {{ 'line-color': '#ffffff', 'line-width': 9, 'line-opacity': 0.95 }},
    layout: {{ 'line-cap': 'round', 'line-join': 'round' }}
  }});
  map.addLayer({{
    id: lineId, type: 'line', source: sourceId,
    paint: {{ 'line-color': d.color, 'line-width': 5, 'line-opacity': 0.95 }},
    layout: {{ 'line-cap': 'round', 'line-join': 'round' }}
  }});

  var coords = d.route_coords;
  var numSegs = coords.length - 1;
  var maxArrows = Math.min(12, Math.max(3, Math.floor(numSegs / 4)));
  var step = Math.max(1, Math.floor(numSegs / maxArrows));
  for (var i = step; i < numSegs; i += step) {{
    var c1 = coords[Math.max(0, i - 1)], c2 = coords[i];
    var dx = c2[0] - c1[0], dy = c2[1] - c1[1];
    if (Math.abs(dx) < 0.00005 && Math.abs(dy) < 0.00005) continue;
    var angle = Math.atan2(dy, dx) * 180 / Math.PI;
    var el = document.createElement('div');
    el.className = 'arrow-marker';
    el.style.background = d.color;
    el.style.transform = 'rotate(' + (-angle + 90) + 'deg)';
    el.textContent = '▲';
    arrows.push(new maplibregl.Marker({{ element: el }}).setLngLat(c2).addTo(map));
  }}

  d.markers.forEach(function(m) {{
    var el = document.createElement('div');
    el.className = 'marker marker-place';
    el.style.background = d.color;
    el.textContent = String(m.num);
    el.title = 'День ' + d.day_number + ': ' + m.name;
    var popup = new maplibregl.Popup({{ offset: 20, closeButton: true, maxWidth: '280px' }}).setHTML(m.popup);
    markers.push(new maplibregl.Marker({{ element: el }}).setLngLat([m.lon, m.lat]).setPopup(popup).addTo(map));
  }});

  dayObjects[d.day_number] = {{ markers: markers, arrows: arrows, sourceId: sourceId, layerIds: [outlineId, lineId] }};
}}

function destroyDay(dayNum) {{
  var obj = dayObjects[dayNum];
  if (!obj) return;
  obj.markers.forEach(function(m) {{ m.remove(); }});
  obj.arrows.forEach(function(a) {{ a.remove(); }});
  obj.layerIds.forEach(function(id) {{ if (map.getLayer(id)) map.removeLayer(id); }});
  if (map.getSource(obj.sourceId)) map.removeSource(obj.sourceId);
  delete dayObjects[dayNum];
}}

function toggleDay(dayNum, show) {{
  if (show) {{
    if (dayObjects[dayNum]) return;
    var d = DAYS.find(function(x) {{ return x.day_number === dayNum; }});
    if (d) buildDay(d);
  }} else {{
    destroyDay(dayNum);
  }}
  scheduleViewportSync(0);
}}

function toggleAll(show) {{
  document.querySelectorAll('.day-row input[type="checkbox"]').forEach(function(cb) {{
    var dayNum = parseInt(cb.closest('.day-row').getAttribute('data-day'));
    cb.checked = show;
    toggleDay(dayNum, show);
  }});
}}

function toggleSidebar() {{
  var sb = document.getElementById('sidebar');
  sb.classList.toggle('collapsed');
  var btn = sb.querySelector('.collapse-btn');
  btn.textContent = sb.classList.contains('collapsed') ? '+' : '−';
  scheduleViewportSync(30);
}}

window.addEventListener('resize', function() {{
  scheduleViewportSync(0);
}});

window.addEventListener('load', function() {{
  scheduleViewportSync(0);
  scheduleViewportSync(120);
}});

map.on('load', function() {{
  var wrap = document.createElement('div');
  wrap.className = 'hotel-wrap';
  var h = document.createElement('div');
  h.className = 'marker marker-hotel';
  h.textContent = '🏨';
  h.title = HOTEL.name;
  var label = document.createElement('div');
  label.className = 'hotel-label';
  label.textContent = 'Старт / Финиш';
  wrap.appendChild(h);
  wrap.appendChild(label);
  new maplibregl.Marker({{ element: wrap }}).setLngLat([HOTEL.lon, HOTEL.lat]).addTo(map);

  DAYS.forEach(buildDay);
  scheduleViewportSync(0);
  scheduleViewportSync(120);

  if (!initialIdleSyncDone) {{
    map.once('idle', function() {{
      initialIdleSyncDone = true;
      scheduleViewportSync(0);
    }});
  }}

  if (window.ResizeObserver) {{
    viewportObserver = new ResizeObserver(function() {{
      scheduleViewportSync(0);
    }});
    var mapEl = document.getElementById('map');
    if (mapEl) viewportObserver.observe(mapEl);
    viewportObserver.observe(document.body);
  }}
}});
</script></body></html>"""


def generate_route_map(plan: TravelPlan) -> str:
    days_data, min_lon, min_lat, max_lon, max_lat = _collect_map_data(plan)
    bounds = (min_lon, min_lat, max_lon, max_lat)
    sidebar_html = _build_sidebar(plan, days_data)

    use_twogis = _is_twogis_region(plan.hotel.lon, plan.hotel.lat) and settings.geo_api_key
    renderer = '2GIS' if use_twogis else 'MapLibre'
    logger.info('Map renderer: %s for %s (%.4f, %.4f)', renderer, plan.destination, plan.hotel.lon, plan.hotel.lat)

    if use_twogis:
        return _render_twogis(plan, days_data, bounds, sidebar_html)
    return _render_maplibre(plan, days_data, bounds, sidebar_html)
