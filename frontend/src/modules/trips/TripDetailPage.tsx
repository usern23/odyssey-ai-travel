import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router';
import { ArrowLeft, MapPin, Clock, Footprints, Calendar, Star, RefreshCw } from 'lucide-react';
import { api, ApiError, type TripItem } from '@/shared/api';
import { useAuth } from '@/modules/auth';

const DAY_COLORS = [
  '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
  '#EC4899', '#06B6D4', '#F97316',
];

interface Place {
  name: string;
  lat: number;
  lon: number;
  category: string;
  description?: string;
  rating?: number;
  visit_duration_min?: number;
}

interface Activity {
  place: Place;
  start_time: string;
  end_time: string;
  travel_time_from_prev_min: number;
  travel_distance_from_prev_km: number;
}

interface DayPlan {
  day_number: number;
  date: string;
  activities: Activity[];
  route_geometry?: string;
  total_distance_km: number;
  total_travel_time_min: number;
  total_visit_time_min: number;
}

interface PlanData {
  destination: string;
  hotel: Place;
  days: DayPlan[];
  total_places: number;
  total_distance_km: number;
  total_travel_time_min: number;
}

function categoryLabel(cat: string): string {
  const labels: Record<string, string> = {
    museum: 'Музей', landmark: 'Достопримечательность', restaurant: 'Ресторан',
    cafe: 'Кафе', park: 'Парк', beach: 'Пляж', shopping: 'Шопинг',
    entertainment: 'Развлечение', nightlife: 'Ночная жизнь', religious: 'Религия',
    nature: 'Природа', viewpoint: 'Обзорная точка', hotel: 'Отель',
  };
  return labels[cat] || cat;
}

const CATEGORY_EMOJI: Record<string, string> = {
  museum: '🏛️', landmark: '🏰', restaurant: '🍽️', cafe: '☕',
  park: '🌳', beach: '🏖️', shopping: '🛍️', entertainment: '🎭',
  nightlife: '🌙', religious: '⛪', nature: '🌿', viewpoint: '🔭',
  hotel: '🏨', transport: '🚌', other: '📍',
};

const TWOGIS_KEY = import.meta.env.VITE_2GIS_KEY || '';

// Регионы с покрытием 2GIS (Россия, Казахстан, ОАЭ и т.д.)
const TWOGIS_REGIONS: [number,number,number,number][] = [
  [27,41,180,82],[46,40,88,56],[56,37,74,46],[69,39,81,44],[51,22.5,56.5,26.5],[29,24,35,32],
];
function isTwogisRegion(lon: number, lat: number) {
  return TWOGIS_KEY && TWOGIS_REGIONS.some(([a,b,c,d]) => lon>=a && lon<=c && lat>=b && lat<=d);
}

function collectMapData(plan: PlanData, visibleDays: DayPlan[]) {
  const hotel = plan.hotel;
  const allLons = [hotel.lon], allLats = [hotel.lat];
  const esc = (s: string) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const days: { dayNum: number; color: string; markers: { lon: number; lat: number; num: number; name: string; popup: string }[]; coords: number[][] }[] = [];

  for (const day of visibleDays) {
    if (!day.activities.length) continue;
    const color = DAY_COLORS[(day.day_number - 1) % DAY_COLORS.length];
    const routeCoords: number[][] = [[hotel.lon, hotel.lat]];
    const markers: typeof days[0]['markers'] = [];

    for (let i = 0; i < day.activities.length; i++) {
      const act = day.activities[i];
      const p = act.place;
      allLons.push(p.lon); allLats.push(p.lat);
      routeCoords.push([p.lon, p.lat]);
      const emoji = CATEGORY_EMOJI[p.category] || '📍';
      const catLabel = categoryLabel(p.category);
      const ratingStr = p.rating ? ` · ⭐ ${p.rating}` : '';
      const timeStr = `${(act.start_time||'').slice(0,5)} – ${(act.end_time||'').slice(0,5)}`;
      const popup = `<b>${esc(p.name)}</b><br>${emoji} ${catLabel}${ratingStr}<br>⏰ ${timeStr}`;
      markers.push({ lon: p.lon, lat: p.lat, num: i+1, name: esc(p.name), popup });
    }

    routeCoords.push([hotel.lon, hotel.lat]);
    let finalCoords = routeCoords;
    if (day.route_geometry) {
      try { const g = JSON.parse(day.route_geometry); if (g.coordinates) finalCoords = g.coordinates; } catch {}
    }
    days.push({ dayNum: day.day_number, color, markers, coords: finalCoords });
  }

  const pad = 0.005;
  return {
    days, hotel: { lon: hotel.lon, lat: hotel.lat, name: esc(hotel.name) },
    bounds: [Math.min(...allLons)-pad, Math.min(...allLats)-pad, Math.max(...allLons)+pad, Math.max(...allLats)+pad] as [number,number,number,number],
  };
}

function buildTwogisHtml(data: ReturnType<typeof collectMapData>): string {
  const { hotel, days, bounds } = data;
  const [minLon,minLat,maxLon,maxLat] = bounds;
  const cx = (minLon+maxLon)/2, cy = (minLat+maxLat)/2;

  let markersJs = `new mapgl.HtmlMarker(map,{coordinates:[${hotel.lon},${hotel.lat}],html:'<div style="background:#1E293B;color:#fff;width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.4);cursor:pointer">🏨</div>'});`;
  let polylinesJs = '';

  for (const d of days) {
    for (const m of d.markers) {
      markersJs += `(function(){var mk=new mapgl.HtmlMarker(map,{coordinates:[${m.lon},${m.lat}],html:'<div style="background:${d.color};color:#fff;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.3);cursor:pointer">${m.num}</div>'});mk.getElement().addEventListener("click",function(){showPopup([${m.lon},${m.lat}],'${m.popup.replace(/'/g,"&#39;")}')})})();`;
    }
    polylinesJs += `new mapgl.Polyline(map,{coordinates:${JSON.stringify(d.coords)},width:4,color:'${d.color}'});`;
  }

  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:100%;height:100%;overflow:hidden}#map{width:100%;height:100%}
.popup-overlay{position:fixed;top:0;left:0;right:0;bottom:0;display:none;z-index:9999;pointer-events:none}
.popup-card{position:absolute;background:#fff;border-radius:12px;padding:12px 16px;box-shadow:0 4px 20px rgba(0,0,0,.2);font-family:-apple-system,sans-serif;font-size:13px;line-height:1.5;max-width:260px;pointer-events:auto}
.popup-card b{font-size:14px}.popup-close{position:absolute;top:6px;right:10px;cursor:pointer;font-size:18px;color:#999;background:none;border:none}</style></head>
<body><div id="map"></div>
<div class="popup-overlay" id="popupOverlay" onclick="closePopup()"><div class="popup-card" id="popupCard" onclick="event.stopPropagation()"><button class="popup-close" onclick="closePopup()">×</button><div id="popupContent"></div></div></div>
<script src="https://mapgl.2gis.com/api/js/v1"></script>
<script>
var map=new mapgl.Map('map',{center:[${cx},${cy}],zoom:13,key:'${TWOGIS_KEY}',lang:'ru',zoomControl:'topRight'});
map.fitBounds({southWest:[${minLon},${minLat}],northEast:[${maxLon},${maxLat}],padding:{top:50,bottom:50,left:50,right:50}});
function showPopup(c,h){var p=map.project(c);var card=document.getElementById('popupCard');document.getElementById('popupContent').innerHTML=h;card.style.left=Math.min(p[0],window.innerWidth-280)+'px';card.style.top=Math.max(p[1]-100,10)+'px';document.getElementById('popupOverlay').style.display='block'}
function closePopup(){document.getElementById('popupOverlay').style.display='none'}
${markersJs}
${polylinesJs}
</script></body></html>`;
}

function buildMaplibreHtml(data: ReturnType<typeof collectMapData>): string {
  const { hotel, days, bounds } = data;
  const [minLon,minLat,maxLon,maxLat] = bounds;

  const markerFeatures = [{
    type:'Feature', geometry:{type:'Point',coordinates:[hotel.lon,hotel.lat]},
    properties:{type:'hotel',label:'🏨',popup:`<b>🏨 ${hotel.name}</b><br>Отель`,color:'#1E293B'}
  }];
  const lineFeatures: object[] = [];

  for (const d of days) {
    for (const m of d.markers) {
      markerFeatures.push({
        type:'Feature', geometry:{type:'Point',coordinates:[m.lon,m.lat]},
        properties:{type:'place',label:String(m.num),popup:m.popup,color:d.color}
      });
    }
    lineFeatures.push({
      type:'Feature', geometry:{type:'LineString',coordinates:d.coords},
      properties:{color:d.color,day:d.dayNum}
    });
  }

  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:100%;height:100%;overflow:hidden}#map{width:100%;height:100%}
.marker{display:flex;align-items:center;justify-content:center;border-radius:50%;color:#fff;font-weight:700;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35);cursor:pointer;transition:transform .15s}
.marker:hover{transform:scale(1.15)}.marker-hotel{width:36px;height:36px;font-size:18px;border-width:3px}.marker-place{width:28px;height:28px;font-size:13px}
.maplibregl-popup-content{border-radius:12px!important;padding:12px 16px!important;box-shadow:0 4px 20px rgba(0,0,0,.18)!important;font-size:13px;line-height:1.5}
.maplibregl-popup-content b{font-size:14px}.maplibregl-popup-close-button{font-size:18px;color:#999;padding:4px 8px}</style></head>
<body><div id="map"></div>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script>
var markers=${JSON.stringify(markerFeatures)};
var lines=${JSON.stringify(lineFeatures)};
var map=new maplibregl.Map({container:'map',style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:''}},layers:[{id:'osm',type:'raster',source:'osm'}]},center:[0,0],zoom:2});
map.fitBounds([[${minLon},${minLat}],[${maxLon},${maxLat}]],{padding:50});
map.on('load',function(){
lines.forEach(function(l,i){map.addSource('r-'+i,{type:'geojson',data:l});map.addLayer({id:'rl-'+i,type:'line',source:'r-'+i,paint:{'line-color':l.properties.color,'line-width':4,'line-opacity':0.8},layout:{'line-cap':'round','line-join':'round'}})});
markers.forEach(function(f){var el=document.createElement('div');el.className='marker '+(f.properties.type==='hotel'?'marker-hotel':'marker-place');el.style.background=f.properties.color;el.textContent=f.properties.label;var p=new maplibregl.Popup({offset:18,closeButton:true,maxWidth:'260px'}).setHTML(f.properties.popup);new maplibregl.Marker({element:el}).setLngLat(f.geometry.coordinates).setPopup(p).addTo(map)})});
</script></body></html>`;
}

function buildMapHtml(plan: PlanData, visibleDays: DayPlan[]): string {
  const data = collectMapData(plan, visibleDays);
  if (isTwogisRegion(plan.hotel.lon, plan.hotel.lat)) {
    return buildTwogisHtml(data);
  }
  return buildMaplibreHtml(data);
}

function TripMap({ plan, visibleDays }: { plan: PlanData; visibleDays: DayPlan[] }) {
  const html = useMemo(() => buildMapHtml(plan, visibleDays), [plan, visibleDays]);
  return (
    <iframe
      srcDoc={html}
      style={{ width: '100%', height: '100%', border: 'none' }}
      sandbox="allow-scripts allow-same-origin"
      title="Trip route map"
    />
  );
}

export default function TripDetailPage() {
  const { tripId } = useParams<{ tripId: string }>();
  const navigate = useNavigate();
  const { isAuthenticated, logout } = useAuth();
  const [trip, setTrip] = useState<TripItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeDay, setActiveDay] = useState<number | null>(null);
  // Replan UI state: the day currently being edited, selected "already visited" places,
  // and the datetime cut-off (ISO local format, datetime-local input).
  const [replanDay, setReplanDay] = useState<number | null>(null);
  const [replanVisited, setReplanVisited] = useState<Set<string>>(new Set());
  const [replanTime, setReplanTime] = useState<string>('');
  const [replanLoading, setReplanLoading] = useState(false);
  const [replanError, setReplanError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) { navigate('/login'); return; }
    if (!tripId) return;
    (async () => {
      try {
        const data = await api.getTrip(Number(tripId));
        setTrip(data);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) { logout(); navigate('/login'); }
      } finally {
        setLoading(false);
      }
    })();
  }, [tripId, isAuthenticated]);

  const plan: PlanData | null = useMemo(() => {
    if (!trip?.generated_plan || !trip.generated_plan.plan_data) return null;
    return trip.generated_plan.plan_data as PlanData;
  }, [trip]);

  const visibleDays = useMemo(() => {
    if (!plan) return [];
    if (activeDay === null) return plan.days;
    return plan.days.filter((d) => d.day_number === activeDay);
  }, [plan, activeDay]);

  // Format a Date into the value format expected by <input type="datetime-local">.
  const formatDatetimeLocal = (d: Date) => {
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const openReplanPanel = (dayNumber: number) => {
    setReplanDay(dayNumber);
    setReplanVisited(new Set());
    setReplanTime(formatDatetimeLocal(new Date()));
    setReplanError(null);
  };

  const closeReplanPanel = () => {
    if (replanLoading) return;
    setReplanDay(null);
    setReplanVisited(new Set());
    setReplanError(null);
  };

  const toggleVisited = (placeName: string) => {
    setReplanVisited((prev) => {
      const next = new Set(prev);
      if (next.has(placeName)) next.delete(placeName);
      else next.add(placeName);
      return next;
    });
  };

  const submitReplan = async () => {
    if (!trip || replanDay === null) return;
    setReplanLoading(true);
    setReplanError(null);
    try {
      // The backend expects a naive ISO string (no tz). datetime-local already gives us that.
      const body: { current_datetime_iso?: string; visited_place_names?: string[] } = {};
      if (replanTime) body.current_datetime_iso = replanTime;
      if (replanVisited.size > 0) body.visited_place_names = Array.from(replanVisited);
      const updated = await api.replanTripDay(trip.id, replanDay, body);
      setTrip(updated);
      setReplanDay(null);
      setReplanVisited(new Set());
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) { logout(); navigate('/login'); return; }
        setReplanError(err.message || `Ошибка ${err.status}`);
      } else {
        setReplanError('Неизвестная ошибка при перепланировании');
      }
    } finally {
      setReplanLoading(false);
    }
  };

  if (loading) {
    return <div className="min-h-screen bg-slate-50 dark:bg-black flex items-center justify-center text-slate-400">Загрузка...</div>;
  }

  if (!trip) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-black flex flex-col items-center justify-center gap-4">
        <p className="text-slate-400">Поездка не найдена</p>
        <button onClick={() => navigate('/trips')} className="text-blue-500 hover:underline">← Назад</button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black">
      {/* Header */}
      <div className="bg-gradient-to-br from-blue-600 to-indigo-700 text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <button onClick={() => navigate('/trips')} className="flex items-center gap-1 text-white/70 hover:text-white mb-4 text-sm">
            <ArrowLeft size={16} /> Мои поездки
          </button>
          <h1 className="text-3xl font-bold mb-2">{trip.name}</h1>
          <div className="flex flex-wrap gap-4 text-white/80 text-sm">
            {trip.start_date && trip.end_date && (
              <span className="flex items-center gap-1"><Calendar size={14} />{new Date(trip.start_date).toLocaleDateString('ru-RU')} — {new Date(trip.end_date).toLocaleDateString('ru-RU')}</span>
            )}
            {plan && (
              <>
                <span className="flex items-center gap-1"><MapPin size={14} />{plan.total_places} мест</span>
                <span className="flex items-center gap-1"><Footprints size={14} />{plan.total_distance_km.toFixed(1)} км</span>
                <span className="flex items-center gap-1"><Clock size={14} />{Math.round(plan.total_travel_time_min)} мин в пути</span>
              </>
            )}
          </div>
        </div>
      </div>

      {!plan ? (
        <div className="max-w-7xl mx-auto px-4 py-20 text-center">
          <MapPin size={48} className="mx-auto mb-4 text-slate-300 dark:text-slate-600" />
          <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-300 mb-2">Маршрут ещё не сгенерирован</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">Попросите ИИ-планировщик создать маршрут в чате.</p>
          <button onClick={() => navigate('/chat')} className="px-6 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors">
            Открыть чат
          </button>
        </div>
      ) : (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {/* Day tabs */}
          <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
            <button
              onClick={() => setActiveDay(null)}
              className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-colors ${
                activeDay === null
                  ? 'bg-slate-900 dark:bg-white text-white dark:text-black'
                  : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            >
              Все дни
            </button>
            {plan.days.map((day) => (
              <button
                key={day.day_number}
                onClick={() => setActiveDay(day.day_number)}
                className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-colors ${
                  activeDay === day.day_number
                    ? 'text-white'
                    : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
                style={activeDay === day.day_number ? { background: DAY_COLORS[(day.day_number - 1) % DAY_COLORS.length] } : {}}
              >
                День {day.day_number}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            {/* Map */}
            <div className="lg:col-span-3 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm" style={{ height: 520 }}>
              <TripMap plan={plan} visibleDays={visibleDays} />
            </div>

            {/* Day itinerary */}
            <div className="lg:col-span-2 space-y-4 max-h-[520px] overflow-y-auto pr-1">
              {visibleDays.map((day) => {
                const color = DAY_COLORS[(day.day_number - 1) % DAY_COLORS.length];
                return (
                  <div key={day.day_number} className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <div className="w-3 h-3 rounded-full" style={{ background: color }} />
                      <h3 className="font-bold text-slate-900 dark:text-white">
                        День {day.day_number}
                      </h3>
                      <span className="text-xs text-slate-400 ml-auto">
                        {new Date(day.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}
                      </span>
                      <button
                        onClick={() => (replanDay === day.day_number ? closeReplanPanel() : openReplanPanel(day.day_number))}
                        disabled={replanLoading && replanDay !== day.day_number}
                        className="ml-1 flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50"
                        title="Перепланировать этот день с учётом текущего времени и погоды"
                      >
                        <RefreshCw size={12} />
                        {replanDay === day.day_number ? 'Закрыть' : 'Перепланировать'}
                      </button>
                    </div>
                    {replanDay === day.day_number && (
                      <div className="mb-4 p-3 rounded-lg border border-blue-200 dark:border-blue-900 bg-blue-50/50 dark:bg-blue-950/30 text-xs space-y-3">
                        <div>
                          <label className="block text-slate-600 dark:text-slate-300 mb-1 font-medium">Текущее время</label>
                          <input
                            type="datetime-local"
                            value={replanTime}
                            onChange={(e) => setReplanTime(e.target.value)}
                            className="w-full px-2 py-1 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
                          />
                        </div>
                        {day.activities.length > 0 && (
                          <div>
                            <div className="text-slate-600 dark:text-slate-300 mb-1 font-medium">Уже посещённые места</div>
                            <div className="space-y-1 max-h-32 overflow-y-auto">
                              {day.activities.map((act, idx) => (
                                <label key={idx} className="flex items-center gap-2 cursor-pointer">
                                  <input
                                    type="checkbox"
                                    checked={replanVisited.has(act.place.name)}
                                    onChange={() => toggleVisited(act.place.name)}
                                    className="accent-blue-600"
                                  />
                                  <span className="text-slate-700 dark:text-slate-200 truncate">{act.place.name}</span>
                                </label>
                              ))}
                            </div>
                          </div>
                        )}
                        {replanError && (
                          <div className="text-red-600 dark:text-red-400">{replanError}</div>
                        )}
                        <div className="flex gap-2">
                          <button
                            onClick={submitReplan}
                            disabled={replanLoading}
                            className="flex-1 px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white font-medium disabled:opacity-60"
                          >
                            {replanLoading ? 'Пересчитываем…' : 'Перепланировать день'}
                          </button>
                          <button
                            onClick={closeReplanPanel}
                            disabled={replanLoading}
                            className="px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-60"
                          >
                            Отмена
                          </button>
                        </div>
                      </div>
                    )}
                    <div className="text-xs text-slate-500 dark:text-slate-400 flex gap-3 mb-4">
                      <span>{day.activities.length} мест</span>
                      <span>{day.total_distance_km.toFixed(1)} км</span>
                      <span>{day.total_travel_time_min} мин</span>
                    </div>
                    <div className="space-y-3">
                      {day.activities.map((act, i) => (
                        <div key={i} className="flex gap-3">
                          <div className="flex flex-col items-center">
                            <div
                              className="w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0"
                              style={{ background: color }}
                            >
                              {i + 1}
                            </div>
                            {i < day.activities.length - 1 && (
                              <div className="w-px flex-1 bg-slate-200 dark:bg-slate-700 my-1" />
                            )}
                          </div>
                          <div className="flex-1 pb-3">
                            <div className="font-medium text-sm text-slate-900 dark:text-white">{act.place.name}</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                              {categoryLabel(act.place.category)}
                              {act.place.rating ? ` · ⭐ ${act.place.rating}` : ''}
                            </div>
                            <div className="text-xs text-slate-400 mt-0.5">
                              {act.start_time?.slice(0, 5)} — {act.end_time?.slice(0, 5)}
                              {act.travel_time_from_prev_min > 0 && (
                                <span className="ml-2">🚶 {act.travel_time_from_prev_min} мин</span>
                              )}
                            </div>
                            {act.place.description && (
                              <div className="text-xs text-slate-400 mt-1 line-clamp-2">{act.place.description}</div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
              {visibleDays.every((d) => d.activities.length === 0) && (
                <div className="text-center text-slate-400 py-10">Нет активностей</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
