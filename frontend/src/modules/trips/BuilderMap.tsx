import { useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { TravelPlanDto } from '@/shared/api';
import { DAY_COLORS, isTwogisRegion, get2gisKey } from './mapUtils';

// Build a 2GIS HTML page (embedded into an iframe) showing
// the same plan as the Leaflet view. Used for regions covered by 2GIS
// (Russia, Kazakhstan, UAE, etc.) so the trip detail page and the builder
// page show the *same* tiles for the *same* trip.
function buildTwogisHtml(plan: TravelPlanDto, visibleDays: TravelPlanDto['days']): string {
  const TWOGIS_KEY = get2gisKey();
  const hotel = plan.hotel;
  const allLons: number[] = [hotel.lon];
  const allLats: number[] = [hotel.lat];
  let markersJs = `new mapgl.HtmlMarker(map,{coordinates:[${hotel.lon},${hotel.lat}],html:'<div style=\\"background:#0f172a;color:#fbbf24;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;border:2px solid #fbbf24;box-shadow:0 2px 8px rgba(0,0,0,.4)\\">★</div>'});`;
  let polylinesJs = '';
  for (const day of visibleDays) {
    if (!day.activities.length) continue;
    const color = DAY_COLORS[(day.day_number - 1) % DAY_COLORS.length];
    const coords: number[][] = [[hotel.lon, hotel.lat]];
    for (let i = 0; i < day.activities.length; i++) {
      const a = day.activities[i];
      allLons.push(a.place.lon);
      allLats.push(a.place.lat);
      coords.push([a.place.lon, a.place.lat]);
      markersJs += `new mapgl.HtmlMarker(map,{coordinates:[${a.place.lon},${a.place.lat}],html:'<div style=\\"background:${color};color:#fff;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.3)\\">${i + 1}</div>'});`;
    }
    coords.push([hotel.lon, hotel.lat]);
    polylinesJs += `new mapgl.Polyline(map,{coordinates:${JSON.stringify(coords)},width:4,color:'${color}'});`;
  }
  const pad = 0.005;
  const minLon = Math.min(...allLons) - pad;
  const maxLon = Math.max(...allLons) + pad;
  const minLat = Math.min(...allLats) - pad;
  const maxLat = Math.max(...allLats) + pad;
  const cx = (minLon + maxLon) / 2, cy = (minLat + maxLat) / 2;
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:100%;height:100%;overflow:hidden}#map{width:100%;height:100%}</style>
</head><body><div id="map"></div>
<script src="https://mapgl.2gis.com/api/js/v1"></script>
<script>
var map=new mapgl.Map('map',{center:[${cx},${cy}],zoom:13,key:'${TWOGIS_KEY}',lang:'ru',zoomControl:'topRight'});
map.fitBounds({southWest:[${minLon},${minLat}],northEast:[${maxLon},${maxLat}],padding:{top:50,bottom:50,left:50,right:50}});
${markersJs}
${polylinesJs}
</script></body></html>`;
}

function buildNumberedIcon(num: number, color: string): L.DivIcon {
  return L.divIcon({
    className: 'odyssey-builder-marker',
    html: `<div style="
      background:${color};color:white;border:2px solid white;border-radius:50%;
      width:28px;height:28px;display:flex;align-items:center;justify-content:center;
      font-size:13px;font-weight:700;box-shadow:0 1px 4px rgba(0,0,0,0.3);
    ">${num}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -14],
  });
}

function buildHotelIcon(): L.DivIcon {
  return L.divIcon({
    className: 'odyssey-builder-hotel',
    html: `<div style="
      background:#0f172a;color:#fbbf24;border:2px solid #fbbf24;border-radius:50%;
      width:32px;height:32px;display:flex;align-items:center;justify-content:center;
      font-size:16px;box-shadow:0 1px 4px rgba(0,0,0,0.4);
    ">★</div>`,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -16],
  });
}

function FitBounds({ bounds }: { bounds: L.LatLngBoundsExpression | null }) {
  const map = useMap();
  useEffect(() => {
    if (!bounds) return;
    map.fitBounds(bounds, { padding: [40, 40] });
  }, [bounds, map]);
  return null;
}

interface BuilderMapProps {
  plan: TravelPlanDto;
  selectedDay: number | 'all';
}

export default function BuilderMap({ plan, selectedDay }: BuilderMapProps) {
  const visibleDays = useMemo(() => {
    if (selectedDay === 'all') return plan.days;
    return plan.days.filter((d) => d.day_number === selectedDay);
  }, [plan.days, selectedDay]);

  const useTwogis = isTwogisRegion(plan.hotel.lon, plan.hotel.lat);

  // 2GIS branch: embed the same iframe-based renderer as TripDetailPage.
  const twogisHtml = useMemo(
    () => (useTwogis ? buildTwogisHtml(plan, visibleDays) : ''),
    [useTwogis, plan, visibleDays],
  );

  if (useTwogis) {
    return (
      <iframe
        srcDoc={twogisHtml}
        style={{ width: '100%', height: '100%', border: 'none', borderRadius: 12 }}
        sandbox="allow-scripts allow-same-origin"
        title="Trip route map (2GIS)"
      />
    );
  }

  const bounds = ((): L.LatLngBoundsExpression | null => {
    const points: [number, number][] = [[plan.hotel.lat, plan.hotel.lon]];
    for (const d of visibleDays) {
      for (const a of d.activities) points.push([a.place.lat, a.place.lon]);
    }
    if (points.length < 2) return null;
    return L.latLngBounds(points.map(([lat, lon]) => L.latLng(lat, lon)));
  })();

  return (
    <MapContainer
      center={[plan.hotel.lat, plan.hotel.lon]}
      zoom={13}
      scrollWheelZoom
      attributionControl={false}
      style={{ height: '100%', width: '100%', borderRadius: 12 }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds bounds={bounds} />
      <Marker position={[plan.hotel.lat, plan.hotel.lon]} icon={buildHotelIcon()}>
        <Popup><b>{plan.hotel.name}</b><br />Отель</Popup>
      </Marker>
      {visibleDays.map((day) => {
        const color = DAY_COLORS[(day.day_number - 1) % DAY_COLORS.length];
        const fallback: [number, number][] = [
          [plan.hotel.lat, plan.hotel.lon],
          ...day.activities.map((a) => [a.place.lat, a.place.lon] as [number, number]),
        ];
        if (day.activities.length > 0) fallback.push([plan.hotel.lat, plan.hotel.lon]);
        // Prefer real ORS geometry; coords come as [lon,lat] in GeoJSON,
        // Leaflet wants [lat,lon].
        const realCoords = parseRouteGeometry(day.route_geometry);
        const route: [number, number][] = (realCoords && realCoords.length >= 2)
          ? realCoords.map((c) => [c[1], c[0]] as [number, number])
          : fallback;
        return (
          <div key={`day-${day.day_number}`}>
            <Polyline positions={route} pathOptions={{ color, weight: 3, opacity: 0.7 }} />
            {day.activities.map((act, idx) => (
              <Marker
                key={`d${day.day_number}-i${idx}`}
                position={[act.place.lat, act.place.lon]}
                icon={buildNumberedIcon(idx + 1, color)}
              >
                <Popup>
                  <b>{act.place.name}</b>
                  <br />
                  День {day.day_number}, {act.start_time?.slice(0, 5)} – {act.end_time?.slice(0, 5)}
                </Popup>
              </Marker>
            ))}
          </div>
        );
      })}
    </MapContainer>
  );
}
