import { useEffect, useRef, useState } from 'react';
import { Search, MapPin, Loader2 } from 'lucide-react';
import { api, ApiError, type PlanPlace } from '@/shared/api';

interface SearchResult {
  name: string;
  lat: number;
  lon: number;
  category: string;
  address?: string | null;
}

interface Props {
  /** Centre of the search (e.g. trip hotel coords). */
  focusLat?: number | null;
  focusLon?: number | null;
  /** Hard filter radius in km around focus. Defaults to 50. */
  radiusKm?: number;
  /** Called when the user picks a result. */
  onPick: (place: PlanPlace) => Promise<void> | void;
  onCancel?: () => void;
  placeholder?: string;
  /** Optional category override applied to picked result. */
  defaultCategory?: string;
  defaultDuration?: number;
}

export default function PlaceSearchInput({
  focusLat, focusLon, radiusKm = 50, onPick, onCancel,
  placeholder = 'Поиск места: Albert Hall, кафе…',
  defaultCategory, defaultDuration = 60,
}: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duration, setDuration] = useState(String(defaultDuration));
  const [picking, setPicking] = useState(false);
  const debounceRef = useRef<number | null>(null);
  const reqIdRef = useRef(0);

  // Debounced search.
  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    if (query.trim().length < 2) {
      setResults([]); setError(null); setLoading(false);
      return;
    }
    setLoading(true);
    const myReq = ++reqIdRef.current;
    debounceRef.current = window.setTimeout(async () => {
      try {
        const res = await api.searchPlaces({
          query: query.trim(),
          near_lat: focusLat ?? null,
          near_lon: focusLon ?? null,
          radius_km: focusLat != null && focusLon != null ? radiusKm : null,
          limit: 8,
        });
        // Drop stale responses.
        if (myReq !== reqIdRef.current) return;
        setResults(res.results);
        setError(null);
      } catch (e) {
        if (myReq !== reqIdRef.current) return;
        const msg = e instanceof ApiError ? e.message : 'Ошибка поиска';
        setError(msg);
        setResults([]);
      } finally {
        if (myReq === reqIdRef.current) setLoading(false);
      }
    }, 350);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [query, focusLat, focusLon, radiusKm]);

  const pick = async (r: SearchResult) => {
    setPicking(true);
    try {
      await onPick({
        name: r.name,
        lat: r.lat,
        lon: r.lon,
        category: defaultCategory ?? r.category ?? 'other',
        visit_duration_min: parseInt(duration, 10) || 60,
        address: r.address ?? undefined,
        source: 'ors',
      });
      setQuery('');
      setResults([]);
    } finally {
      setPicking(false);
    }
  };

  return (
    <div className="space-y-2 bg-slate-50 dark:bg-slate-800/50 rounded-lg p-3">
      <div className="relative">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          className="w-full pl-8 pr-8 py-2 text-sm rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 outline-none focus:ring-2 focus:ring-blue-500"
        />
        {loading && (
          <Loader2 size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 animate-spin" />
        )}
      </div>
      {error && <div className="text-xs text-red-600">{error}</div>}
      {results.length > 0 && (
        <div className="max-h-60 overflow-y-auto rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 divide-y divide-slate-100 dark:divide-slate-800">
          {results.map((r, i) => (
            <button
              key={`${r.lat}-${r.lon}-${i}`}
              onClick={() => pick(r)}
              disabled={picking}
              className="w-full text-left px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-900/20 flex items-start gap-2 disabled:opacity-50"
            >
              <MapPin size={14} className="text-slate-400 mt-0.5 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-sm text-slate-900 dark:text-white truncate font-medium">{r.name}</div>
                {r.address && r.address !== r.name && (
                  <div className="text-xs text-slate-500 truncate">{r.address}</div>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
      {query.trim().length >= 2 && !loading && results.length === 0 && !error && (
        <div className="text-xs text-slate-400 text-center py-1">Ничего не найдено</div>
      )}
      <div className="flex items-center gap-2">
        <label className="text-xs text-slate-500 flex-shrink-0">Длительность:</label>
        <input
          type="number"
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
          className="w-20 px-2 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
        />
        <span className="text-xs text-slate-400">мин</span>
        <div className="flex-1" />
        {onCancel && (
          <button onClick={onCancel} className="text-xs px-2 py-1 text-slate-500 hover:text-slate-800">
            Отмена
          </button>
        )}
      </div>
    </div>
  );
}
