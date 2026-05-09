// Shared map utilities — coverage check for 2GIS regions.
// Bounding boxes (lon_min, lat_min, lon_max, lat_max).
const TWOGIS_REGIONS: [number, number, number, number][] = [
  [27, 41, 180, 82],   // Russia
  [46, 40, 88, 56],    // Kazakhstan
  [56, 37, 74, 46],    // Central Asia
  [69, 39, 81, 44],    // Kyrgyzstan / parts
  [51, 22.5, 56.5, 26.5], // UAE
  [29, 24, 35, 32],    // Cyprus / Egypt edge
];

export function isTwogisRegion(lon: number, lat: number): boolean {
  const key = (import.meta as any).env?.VITE_2GIS_KEY || '';
  if (!key) return false;
  return TWOGIS_REGIONS.some(([a, b, c, d]) => lon >= a && lon <= c && lat >= b && lat <= d);
}

export function get2gisKey(): string {
  return (import.meta as any).env?.VITE_2GIS_KEY || '';
}

export const DAY_COLORS = [
  '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
  '#EC4899', '#06B6D4', '#F97316',
];
