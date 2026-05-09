import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
  ArrowLeft, GripVertical, Lock, Unlock, Trash2, Plus, MapPin,
  Wand2, Heart, MessageSquare, AlertTriangle, Loader2,
  Clock, Footprints, Wallet, StickyNote, Hotel, Pencil, X,
} from 'lucide-react';
import CategoryIcon from './CategoryIcon';
import {
  DndContext, type DragEndEvent, PointerSensor, useSensor, useSensors,
  closestCenter, DragOverlay, type DragStartEvent,
} from '@dnd-kit/core';
import {
  SortableContext, useSortable, arrayMove, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { api, type PlanActivity, type PlanDay, type PlanPlace } from '@/shared/api';
import { useTripBuilder } from './useTripBuilder';
import BuilderMap from './BuilderMap';
import PlaceSearchInput from './PlaceSearchInput';

type DayId = number | 'wishlist';

interface ItemId {
  scope: DayId;
  index: number;
}

function encodeId(id: ItemId): string {
  return `${id.scope}:${id.index}`;
}
function decodeId(s: string): ItemId | null {
  const [scope, idx] = s.split(':');
  if (!scope || idx == null) return null;
  return {
    scope: scope === 'wishlist' ? 'wishlist' : Number(scope),
    index: Number(idx),
  };
}

// Category icons are rendered via the <CategoryIcon /> component
// (see CategoryIcon.tsx). Emojis are kept only inside map markers.

export default function TripBuilderPage() {
  const { tripId: tripIdParam } = useParams<{ tripId: string }>();
  const tripId = Number(tripIdParam);
  const navigate = useNavigate();
  const builder = useTripBuilder(tripId);
  const { plan, trip, loading, saving, error, versionConflict, placeFitError, clearPlaceFitError, reload } = builder;

  const [selectedDayFilter, setSelectedDayFilter] = useState<number | 'all'>('all');
  const [activeDrag, setActiveDrag] = useState<ItemId | null>(null);
  // Days the user has touched since the last optimisation. UI shows
  // an "unoptimised" chip; cleared when user explicitly optimises or
  // manually reorders within the day.
  const [staleDays, setStaleDays] = useState<Set<number>>(new Set());
  const markStale = (d: number) => setStaleDays((s) => {
    if (s.has(d)) return s;
    const n = new Set(s); n.add(d); return n;
  });
  const markFresh = (d: number) => setStaleDays((s) => {
    if (!s.has(d)) return s;
    const n = new Set(s); n.delete(d); return n;
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  const handleDragStart = (e: DragStartEvent) => {
    const id = decodeId(String(e.active.id));
    if (id) setActiveDrag(id);
  };

  const handleDragEnd = async (e: DragEndEvent) => {
    setActiveDrag(null);
    const fromId = decodeId(String(e.active.id));
    const overId = e.over ? decodeId(String(e.over.id)) : null;
    if (!fromId || !overId) return;
    if (fromId.scope === overId.scope && fromId.index === overId.index) return;

    if (fromId.scope === 'wishlist' && overId.scope !== 'wishlist') {
      await builder.promoteFromWishlist(fromId.index, overId.scope as number, overId.index);
      markStale(overId.scope as number);
      return;
    }
    if (fromId.scope !== 'wishlist' && overId.scope === 'wishlist') {
      // Drop into wishlist: take the place out of the day, then add to wishlist.
      const day = plan?.days.find((d) => d.day_number === fromId.scope);
      if (!day) return;
      const place = day.activities[fromId.index]?.place;
      if (!place) return;
      await builder.removeActivity(fromId.scope as number, fromId.index);
      await builder.addToWishlist(place);
      return;
    }
    if (fromId.scope === overId.scope && fromId.scope !== 'wishlist') {
      // Reorder within a day — that's a manual choice; treat as fresh.
      const day = plan?.days.find((d) => d.day_number === fromId.scope);
      if (!day) return;
      const indices = day.activities.map((_, i) => i);
      const next = arrayMove(indices, fromId.index, overId.index);
      await builder.reorderDay(fromId.scope as number, next);
      markFresh(fromId.scope as number);
      return;
    }
    if (fromId.scope !== 'wishlist' && overId.scope !== 'wishlist') {
      // Move across days.
      await builder.movePlace(
        fromId.scope as number, overId.scope as number,
        fromId.index, overId.index,
      );
      markStale(fromId.scope as number);
      markStale(overId.scope as number);
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Загрузка…</div>;
  }
  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-slate-500">
        <AlertTriangle size={32} className="text-red-500" />
        <p>{error}</p>
        <button onClick={reload} className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm">
          Попробовать ещё раз
        </button>
      </div>
    );
  }
  if (!trip || !plan) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">План не найден.</div>;
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter}
                onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="min-h-screen bg-slate-50 dark:bg-black">
        <Header trip={trip} plan={plan} saving={saving} navigate={navigate} tripId={tripId} />
        {versionConflict && (
          <div className="max-w-7xl mx-auto px-4 py-2">
            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700 rounded-lg px-4 py-2 text-sm text-amber-900 dark:text-amber-200 flex items-center gap-2">
              <AlertTriangle size={16} />
              Поездка изменена в другой вкладке (v{versionConflict.actual} вместо v{versionConflict.expected}). Состояние перезагружено.
            </div>
          </div>
        )}
        {placeFitError && (
          <div className="max-w-7xl mx-auto px-4 py-2">
            <div className="bg-rose-50 dark:bg-rose-900/20 border border-rose-300 dark:border-rose-700 rounded-lg px-4 py-3 text-sm text-rose-900 dark:text-rose-200 flex items-start gap-3">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <div className="flex-1">
                <div className="font-medium">{placeFitError.message}</div>
                <div className="text-xs opacity-80 mt-1">
                  Совет: продлите день в <a href="/profile/edit" className="underline">профиле</a> (сейчас до {placeFitError.day_end_hour}:00) или перенесите место в другой день.
                </div>
              </div>
              <button onClick={clearPlaceFitError} className="text-rose-700 dark:text-rose-300 hover:opacity-70 text-xs underline">
                Закрыть
              </button>
            </div>
          </div>
        )}
        <div className="max-w-7xl mx-auto px-4 py-4 space-y-4">
          {/* Hotel as the first item — entry/exit point of the trip */}
          <HotelCard plan={plan} builder={builder} />
          {/* Day filter on its own row so the grid below starts with map and
              the first day card aligned on the same horizontal line. */}
          <DayFilter days={plan.days} value={selectedDayFilter} onChange={setSelectedDayFilter} />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
            {/* Day list — left two columns */}
            <div className="lg:col-span-2 space-y-3">
              {plan.days
                .filter((d) => selectedDayFilter === 'all' || d.day_number === selectedDayFilter)
                .map((day) => (
                  <DayCard
                    key={day.day_number}
                    day={day}
                    builder={builder}
                    isStale={staleDays.has(day.day_number)}
                    onPlaceAdded={() => markStale(day.day_number)}
                    onOptimized={() => markFresh(day.day_number)}
                  />
                ))}
            </div>
            {/* Right column: map + wishlist + budget */}
            <div className="space-y-4">
              <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden h-80">
                <BuilderMap plan={plan} selectedDay={selectedDayFilter} />
              </div>
              <WishlistPanel plan={plan} builder={builder} />
              <BudgetPanel plan={plan} builder={builder} />
            </div>
          </div>
        </div>
      </div>
      <DragOverlay>
        {activeDrag && (
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg px-3 py-2 text-sm opacity-90">
            ⋮⋮ Перенос…
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}

// ════════════════════════════════════════════════════════════════════
// Sub-components
// ════════════════════════════════════════════════════════════════════
function Header({
  trip, plan, saving, navigate, tripId,
}: {
  trip: { name: string }; plan: { version?: number; source?: string };
  saving: boolean; navigate: (p: string) => void; tripId: number;
}) {
  const [askLoading, setAskLoading] = useState(false);
  const askAi = async () => {
    setAskLoading(true);
    try {
      const r = await api.askAiForTrip(tripId);
      console.log('[TripBuilder] askAiForTrip ->', r);
      // Pass chat_id via location.state (reliable path used by favorites)
      // and as ?chat= for shareable URL fallback.
      navigate(`/chat?chat=${r.chat_id}`, { state: { chatId: r.chat_id } });
    } finally {
      setAskLoading(false);
    }
  };
  const sourceColor =
    plan.source === 'manual' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
    : plan.source === 'mixed' ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300'
    : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300';
  return (
    <div className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate(`/trips/${tripId}`)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800">
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-bold truncate text-slate-900 dark:text-white">{trip.name}</h1>
          <div className="flex items-center gap-2 mt-0.5">
            <span className={`text-[11px] font-medium px-1.5 py-0.5 rounded ${sourceColor}`}>
              {plan.source ?? 'agent'}
            </span>
            <span className="text-xs text-slate-400">v{plan.version ?? 1}</span>
            {saving && <span className="text-xs text-slate-400 flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Сохранение</span>}
          </div>
        </div>
        <button
          onClick={askAi}
          disabled={askLoading}
          className="text-sm px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50 flex items-center gap-1.5"
        >
          <MessageSquare size={14} />
          {askLoading ? '…' : 'Спросить ИИ'}
        </button>
      </div>
    </div>
  );
}

function DayFilter({ days, value, onChange }: {
  days: PlanDay[]; value: number | 'all'; onChange: (v: number | 'all') => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <FilterChip active={value === 'all'} onClick={() => onChange('all')}>Все дни</FilterChip>
      {days.map((d) => (
        <FilterChip key={d.day_number} active={value === d.day_number} onClick={() => onChange(d.day_number)}>
          День {d.day_number}
        </FilterChip>
      ))}
    </div>
  );
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
        active
          ? 'bg-blue-600 text-white border-blue-600'
          : 'bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'
      }`}
    >
      {children}
    </button>
  );
}

function DayCard({
  day, builder, isStale, onPlaceAdded, onOptimized,
}: {
  day: PlanDay;
  builder: ReturnType<typeof useTripBuilder>;
  isStale: boolean;
  onPlaceAdded: () => void;
  onOptimized: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [optimizePreview, setOptimizePreview] = useState<{
    added: string[]; removed: string[]; kept: string[];
    before_count: number; after_count: number;
    total_distance_km_before: number; total_distance_km_after: number;
    total_travel_time_min_before: number; total_travel_time_min_after: number;
  } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const ids = useMemo(() => day.activities.map((_, i) => encodeId({ scope: day.day_number, index: i })), [day]);
  const focus = builder.plan?.hotel;

  const dateLabel = useMemo(() => {
    try { return new Date(day.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }); }
    catch { return day.date; }
  }, [day.date]);

  const handleOptimize = async () => {
    if (!builder.trip) return;
    setPreviewLoading(true);
    try {
      const diff = await api.optimizeDayPreview(builder.trip.id, day.day_number, {
        expected_version: builder.plan?.version ?? null,
      });
      setOptimizePreview(diff);
    } catch {
      // Fallback: apply directly if preview fails (e.g. older backend).
      await builder.optimizeDay(day.day_number);
      onOptimized();
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleApplyOptimize = async () => {
    setOptimizePreview(null);
    await builder.optimizeDay(day.day_number);
    onOptimized();
  };

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
      <div className="px-4 py-3 flex items-center justify-between border-b border-slate-100 dark:border-slate-800">
        <div>
          <h3 className="font-bold text-slate-900 dark:text-white text-sm">
            День {day.day_number} <span className="font-normal text-slate-400">· {dateLabel}</span>
          </h3>
          <div className="text-xs text-slate-500 mt-0.5">
            {day.activities.length} мест · {Math.round(day.total_distance_km * 10) / 10} км · {day.total_visit_time_min + day.total_travel_time_min} мин
          </div>
        </div>
        <button
          onClick={handleOptimize}
          disabled={previewLoading}
          className="text-xs px-2 py-1 rounded-md bg-amber-100 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-900/40 flex items-center gap-1 disabled:opacity-50"
          title="Оптимизировать порядок (учитывает локи)"
        >
          <Wand2 size={12} /> {previewLoading ? 'Считаем…' : 'Оптимизировать'}
        </button>
      </div>
      {optimizePreview && (
        <div className="px-4 py-3 bg-blue-50 dark:bg-blue-900/10 border-b border-blue-200 dark:border-blue-900/30 text-xs space-y-2">
          <div className="font-medium text-blue-900 dark:text-blue-200">
            Предпросмотр оптимизации: было {optimizePreview.before_count} → станет {optimizePreview.after_count} мест
          </div>
          {optimizePreview.removed.length > 0 && (
            <div className="text-rose-700 dark:text-rose-300">
              − Удалить: {optimizePreview.removed.join(', ')}
            </div>
          )}
          {optimizePreview.added.length > 0 && (
            <div className="text-emerald-700 dark:text-emerald-300">
              + Добавить: {optimizePreview.added.join(', ')}
            </div>
          )}
          <div className="text-slate-600 dark:text-slate-400">
            Дистанция: {Math.round(optimizePreview.total_distance_km_before * 10) / 10} → {Math.round(optimizePreview.total_distance_km_after * 10) / 10} км ·
            время: {optimizePreview.total_travel_time_min_before} → {optimizePreview.total_travel_time_min_after} мин
          </div>
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleApplyOptimize}
              className="px-3 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white"
            >
              Применить
            </button>
            <button
              onClick={() => setOptimizePreview(null)}
              className="px-3 py-1 rounded border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              Отмена
            </button>
          </div>
        </div>
      )}
      {isStale && day.activities.length >= 2 && (
        <div className="px-4 py-2 bg-amber-50 dark:bg-amber-900/10 border-b border-amber-200 dark:border-amber-900/30 flex items-center justify-between gap-2">
          <span className="text-xs text-amber-800 dark:text-amber-300 flex items-center gap-1.5">
            <AlertTriangle size={12} /> Маршрут не оптимизирован
          </span>
          <button
            onClick={handleOptimize}
            className="text-xs px-2 py-0.5 rounded bg-amber-600 hover:bg-amber-700 text-white flex items-center gap-1"
          >
            <Wand2 size={11} /> Оптимизировать
          </button>
        </div>
      )}
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <div className="divide-y divide-slate-100 dark:divide-slate-800">
          {day.activities.length === 0 && (
            <div className="px-4 py-6 text-sm text-slate-400 text-center">Пока пусто. Добавьте место ниже.</div>
          )}
          {day.activities.map((act, i) => (
            <ActivityCard
              key={`d${day.day_number}-i${i}`}
              id={encodeId({ scope: day.day_number, index: i })}
              activity={act}
              dayNumber={day.day_number}
              activityIndex={i}
              builder={builder}
            />
          ))}
        </div>
      </SortableContext>
      <div className="px-4 py-3 border-t border-slate-100 dark:border-slate-800">
        {adding ? (
          <PlaceSearchInput
            focusLat={focus?.lat ?? null}
            focusLon={focus?.lon ?? null}
            onPick={async (p) => {
              await builder.addPlace(day.day_number, p);
              setAdding(false);
              onPlaceAdded();
            }}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <button
            onClick={() => setAdding(true)}
            className="w-full text-sm py-2 rounded-lg border border-dashed border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50 flex items-center justify-center gap-1"
          >
            <Plus size={14} /> Добавить место
          </button>
        )}
      </div>
    </div>
  );
}

function ActivityCard({
  id, activity, dayNumber, activityIndex, builder,
}: {
  id: string; activity: PlanActivity; dayNumber: number; activityIndex: number;
  builder: ReturnType<typeof useTripBuilder>;
}) {
  const sortable = useSortable({ id });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(sortable.transform),
    transition: sortable.transition,
    opacity: sortable.isDragging ? 0.4 : 1,
  };
  const [editingNote, setEditingNote] = useState(false);
  const [noteValue, setNoteValue] = useState(activity.note ?? '');
  const [editingCost, setEditingCost] = useState(false);
  const [costValue, setCostValue] = useState(
    activity.actual_cost != null ? String(activity.actual_cost) : '',
  );

  const saveNote = async () => {
    setEditingNote(false);
    if ((activity.note ?? '') !== noteValue) {
      await builder.updateActivity(dayNumber, activityIndex, { note: noteValue || null });
    }
  };

  const saveCost = async () => {
    setEditingCost(false);
    const trimmed = costValue.trim();
    const newVal = trimmed === '' ? null : Number(trimmed.replace(',', '.'));
    if (newVal != null && Number.isNaN(newVal)) return;
    if ((activity.actual_cost ?? null) !== newVal) {
      await builder.updateActivity(dayNumber, activityIndex, { actual_cost: newVal });
    }
  };

  return (
    <div ref={sortable.setNodeRef} style={style}
         className="px-4 py-3 flex gap-2 items-start hover:bg-slate-50 dark:hover:bg-slate-800/30">
      <button {...sortable.attributes} {...sortable.listeners}
              className="cursor-grab text-slate-400 hover:text-slate-600 mt-0.5 touch-none">
        <GripVertical size={16} />
      </button>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <CategoryIcon category={activity.place.category} size={14} className="text-slate-500 dark:text-slate-400 flex-shrink-0" />
          <span className="font-medium text-sm text-slate-900 dark:text-white truncate">{activity.place.name}</span>
          {activity.is_locked && <Lock size={12} className="text-amber-500 flex-shrink-0" />}
        </div>
        <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-3 flex-wrap">
          <span className="flex items-center gap-1"><Clock size={11} /> {activity.start_time?.slice(0, 5)} – {activity.end_time?.slice(0, 5)}</span>
          {activity.travel_time_from_prev_min > 0 && <span className="flex items-center gap-1"><Footprints size={11} /> {activity.travel_time_from_prev_min} мин</span>}
          {editingCost ? (
            <span className="flex items-center gap-1">
              <Wallet size={11} />
              <input
                autoFocus
                type="number"
                inputMode="decimal"
                value={costValue}
                onChange={(e) => setCostValue(e.target.value)}
                onBlur={saveCost}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveCost();
                  if (e.key === 'Escape') setEditingCost(false);
                }}
                className="w-14 px-1 text-xs bg-transparent border-b border-slate-300 dark:border-slate-700 focus:outline-none focus:border-blue-500"
                placeholder="0"
              />
            </span>
          ) : activity.actual_cost != null ? (
            <button
              onClick={() => { setCostValue(String(activity.actual_cost ?? '')); setEditingCost(true); }}
              className="flex items-center gap-1 hover:text-slate-800 dark:hover:text-slate-200"
              title="Изменить трату"
            >
              <Wallet size={11} /> {activity.actual_cost}
            </button>
          ) : (
            <button
              onClick={() => { setCostValue(''); setEditingCost(true); }}
              className="text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 italic"
              title="Указать трату"
            >
              + цена
            </button>
          )}
        </div>
        {editingNote ? (
          <input
            autoFocus
            value={noteValue}
            onChange={(e) => setNoteValue(e.target.value)}
            onBlur={saveNote}
            onKeyDown={(e) => { if (e.key === 'Enter') saveNote(); if (e.key === 'Escape') setEditingNote(false); }}
            className="mt-1.5 w-full px-2 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
            placeholder="Заметка…"
          />
        ) : (
          <button onClick={() => { setNoteValue(activity.note ?? ''); setEditingNote(true); }}
                  className="mt-1 text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 italic flex items-center gap-1">
            {activity.note ? <><StickyNote size={11} /> {activity.note}</> : '+ заметка'}
          </button>
        )}
      </div>
      <div className="flex items-center gap-1 flex-shrink-0">
        <button
          onClick={() => builder.updateActivity(dayNumber, activityIndex, { is_locked: !activity.is_locked })}
          className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400 hover:text-amber-500"
          title={activity.is_locked ? 'Разблокировать' : 'Зафиксировать'}
        >
          {activity.is_locked ? <Lock size={14} /> : <Unlock size={14} />}
        </button>
        <button
          onClick={() => builder.removeActivity(dayNumber, activityIndex)}
          className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20 text-slate-400 hover:text-red-500"
          title="Удалить"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}

// ── Wishlist ─────────────────────────────────────────────────────────
function WishlistPanel({ plan, builder }: {
  plan: { wishlist?: PlanPlace[]; hotel?: PlanPlace }; builder: ReturnType<typeof useTripBuilder>;
}) {
  const [adding, setAdding] = useState(false);
  const wishlist = plan.wishlist ?? [];
  const ids = wishlist.map((_, i) => encodeId({ scope: 'wishlist', index: i }));
  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5"><Heart size={14} /> Wishlist</h3>
        <span className="text-xs text-slate-400">{wishlist.length}</span>
      </div>
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <div className="space-y-1.5">
          {wishlist.length === 0 && (
            <div className="text-xs text-slate-400 text-center py-3">Пусто. Сохраняйте идеи здесь.</div>
          )}
          {wishlist.map((p, i) => (
            <WishlistItem key={`wl-${i}`} id={encodeId({ scope: 'wishlist', index: i })}
                          place={p} index={i} builder={builder} />
          ))}
        </div>
      </SortableContext>
      <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-800">
        {adding ? (
          <PlaceSearchInput
            focusLat={plan.hotel?.lat ?? null}
            focusLon={plan.hotel?.lon ?? null}
            onPick={async (p) => { await builder.addToWishlist(p); setAdding(false); }}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <button onClick={() => setAdding(true)}
                  className="w-full text-xs py-1.5 rounded-lg border border-dashed border-slate-300 dark:border-slate-700 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800/50 flex items-center justify-center gap-1">
            <Plus size={12} /> Добавить идею
          </button>
        )}
      </div>
    </div>
  );
}

function WishlistItem({
  id, place, index, builder,
}: { id: string; place: PlanPlace; index: number; builder: ReturnType<typeof useTripBuilder> }) {
  const sortable = useSortable({ id });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(sortable.transform),
    transition: sortable.transition,
    opacity: sortable.isDragging ? 0.4 : 1,
  };
  return (
    <div ref={sortable.setNodeRef} style={style}
         className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-slate-50 dark:bg-slate-800/40 hover:bg-slate-100 dark:hover:bg-slate-800">
      <button {...sortable.attributes} {...sortable.listeners}
              className="cursor-grab text-slate-400 touch-none">
        <GripVertical size={12} />
      </button>
      <span className="flex-shrink-0 text-slate-500 dark:text-slate-400"><CategoryIcon category={place.category} size={13} /></span>
      <div className="flex-1 min-w-0 text-xs text-slate-700 dark:text-slate-200 truncate">{place.name}</div>
      <button onClick={() => builder.removeFromWishlist(index)}
              className="text-slate-400 hover:text-red-500 p-0.5">
        <Trash2 size={11} />
      </button>
    </div>
  );
}

// ── Hotel ──────────────────────────────────────────────────────────
function HotelCard({ plan, builder }: {
  plan: { hotel?: PlanPlace; destination?: string };
  builder: ReturnType<typeof useTripBuilder>;
}) {
  const [editing, setEditing] = useState(false);
  const hotel = plan.hotel ?? null;
  // "Auto" placeholder created when no hotel is supplied looks like
  // "Центр · X" with source='auto'; we treat it as "no hotel".
  const isAuto = !hotel || hotel.source === 'auto' || hotel.name?.startsWith('Центр');

  if (editing) {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
            <Hotel size={14} /> Отель / проживание
          </h3>
          <button onClick={() => setEditing(false)} className="text-slate-400 hover:text-slate-700"><X size={14} /></button>
        </div>
        <PlaceSearchInput
          focusLat={hotel?.lat ?? null}
          focusLon={hotel?.lon ?? null}
          onPick={async (p) => {
            await builder.updateHotel(p);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
        {!isAuto && (
          <button
            onClick={async () => {
              if (!confirm('Сбросить отель? В качестве стартовой точки будет центр города.')) return;
              await builder.updateHotel(null);
              setEditing(false);
            }}
            className="mt-2 w-full text-xs py-1.5 rounded-lg border border-red-200 dark:border-red-900/40 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/10 flex items-center justify-center gap-1"
          >
            <Trash2 size={11} /> Удалить отель
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
          <Hotel size={14} /> Отель / проживание
        </h3>
        <button
          onClick={() => setEditing(true)}
          className="text-xs px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 flex items-center gap-1"
          title={isAuto ? 'Указать отель' : 'Изменить отель'}
        >
          <Pencil size={11} /> {isAuto ? 'Указать' : 'Изменить'}
        </button>
      </div>
      {isAuto ? (
        <div className="text-xs text-slate-500 dark:text-slate-400">
          Не указан. Стартовая точка маршрутов — центр города.
        </div>
      ) : (
        <div>
          <div className="text-sm font-medium text-slate-900 dark:text-white truncate">{hotel!.name}</div>
          {hotel!.address && (
            <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 flex items-center gap-1">
              <MapPin size={11} /> {hotel!.address}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Budget ─────────────────────────────────────────────────────────
// Stable color palette indexed by category name. The mapping is
// deterministic so the same category gets the same colour across
// renders and across the donut + legend.
const BUDGET_PALETTE = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#6366f1',
  '#14b8a6', '#a855f7',
];
const BUDGET_REMAINING_COLOR = '#e2e8f0'; // slate-200

const CATEGORY_RU: Record<string, string> = {
  museum: 'Музеи', landmark: 'Достопримечательности',
  restaurant: 'Рестораны', cafe: 'Кафе', food: 'Еда',
  park: 'Парки', beach: 'Пляжи', shopping: 'Шопинг',
  entertainment: 'Развлечения', nightlife: 'Ночная жизнь',
  religious: 'Религия', nature: 'Природа', viewpoint: 'Виды',
  hotel: 'Отель', transport: 'Транспорт', other: 'Другое',
};

function colorForCategory(category: string, index: number): string {
  // Stable hash → palette index, but fall back to positional index
  // so the donut still looks colourful even with unknown categories.
  let h = 0;
  for (let i = 0; i < category.length; i++) h = (h * 31 + category.charCodeAt(i)) >>> 0;
  return BUDGET_PALETTE[(h + index) % BUDGET_PALETTE.length];
}

function BudgetPanel({ plan, builder }: {
  plan: {
    budget_total?: number | null;
    budget_currency?: string;
    lodging_total?: number | null;
    transport_total?: number | null;
    days?: PlanDay[];
  };
  builder: ReturnType<typeof useTripBuilder>;
}) {
  const [editing, setEditing] = useState(false);
  const [total, setTotal] = useState((plan.budget_total ?? '').toString());
  const [currency, setCurrency] = useState(plan.budget_currency ?? 'RUB');
  const [lodging, setLodging] = useState((plan.lodging_total ?? '').toString());
  const [transport, setTransport] = useState((plan.transport_total ?? '').toString());

  // Aggregate user-entered actual_cost per category across all days,
  // then prepend two synthetic slices for lodging and transport so
  // they participate in the donut + legend exactly like place spend.
  const slices = useMemo(() => {
    const result: Array<{ category: string; label: string; value: number; color: string }> = [];

    if (plan.transport_total && plan.transport_total > 0) {
      result.push({
        category: '__transport',
        label: 'Авиабилеты / транспорт',
        value: plan.transport_total,
        color: '#0ea5e9', // sky-500
      });
    }
    if (plan.lodging_total && plan.lodging_total > 0) {
      result.push({
        category: '__lodging',
        label: 'Проживание',
        value: plan.lodging_total,
        color: '#6366f1', // indigo-500
      });
    }

    const map = new Map<string, number>();
    for (const day of plan.days ?? []) {
      for (const act of day.activities ?? []) {
        const v = act.actual_cost;
        if (v == null || v <= 0) continue;
        const cat = act.place?.category || 'other';
        map.set(cat, (map.get(cat) ?? 0) + Number(v));
      }
    }
    Array.from(map.entries())
      .sort((a, b) => b[1] - a[1])
      .forEach(([category, value], i) => {
        result.push({
          category,
          label: CATEGORY_RU[category] ?? category,
          value,
          color: colorForCategory(category, i),
        });
      });

    return result;
  }, [plan.days, plan.lodging_total, plan.transport_total]);

  const spent = slices.reduce((s, x) => s + x.value, 0);
  const totalBudget = plan.budget_total ?? 0;
  const hasBudget = totalBudget > 0;
  const remaining = hasBudget ? totalBudget - spent : 0;
  const overBudget = hasBudget && spent > totalBudget;
  const cur = plan.budget_currency || 'RUB';

  const save = async () => {
    setEditing(false);
    const parseNum = (s: string): number | null => {
      const t = s.trim();
      if (t === '') return -1; // sentinel: clear
      const n = Number(t.replace(',', '.'));
      return Number.isFinite(n) ? n : null;
    };
    const lodgingVal = parseNum(lodging);
    const transportVal = parseNum(transport);
    await builder.updateBudget({
      total: total === '' ? null : Number(total),
      currency,
      // Pass null when unchanged is unsupported by API, so we always
      // send these two on save. -1 sentinel means "clear" on the server.
      lodging_total: lodgingVal,
      transport_total: transportVal,
    });
  };

  // Donut math — stroke-dasharray slices on a single circle.
  const RADIUS = 38;
  const STROKE = 12;
  const C = 2 * Math.PI * RADIUS;
  // Denominator: when budget is set we draw against budget so the
  // gray "remaining" arc is meaningful. When no budget — against
  // total spent to still show category breakdown.
  const denom = hasBudget ? Math.max(totalBudget, spent) : Math.max(spent, 1);

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
          <Wallet size={14} /> Бюджет
        </h3>
        {!editing && (
          <button
            onClick={() => {
              setTotal((plan.budget_total ?? '').toString());
              setCurrency(plan.budget_currency ?? 'RUB');
              setLodging((plan.lodging_total ?? '').toString());
              setTransport((plan.transport_total ?? '').toString());
              setEditing(true);
            }}
            className="text-xs px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 flex items-center gap-1"
          >
            <Pencil size={11} /> Изменить
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <input
              type="number"
              value={total}
              onChange={(e) => setTotal(e.target.value)}
              placeholder="Сумма"
              className="col-span-2 px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
            />
            <input
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              maxLength={4}
              className="px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
            />
          </div>
          <label className="block text-[11px] text-slate-500 dark:text-slate-400">
            Проживание
            <input
              type="number"
              value={lodging}
              onChange={(e) => setLodging(e.target.value)}
              placeholder="0"
              className="mt-0.5 w-full px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
            />
          </label>
          <label className="block text-[11px] text-slate-500 dark:text-slate-400">
            Авиабилеты / транспорт
            <input
              type="number"
              value={transport}
              onChange={(e) => setTransport(e.target.value)}
              placeholder="0"
              className="mt-0.5 w-full px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950"
            />
          </label>
          <div className="flex gap-2 justify-end">
            <button onClick={() => setEditing(false)} className="text-xs px-2 py-1 text-slate-500">Отмена</button>
            <button onClick={save} className="text-xs px-3 py-1 rounded bg-blue-600 text-white">Сохранить</button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {/* Donut + center text */}
          <div className="flex items-center justify-center">
            <div className="relative" style={{ width: 140, height: 140 }}>
              <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
                {/* Background ring (or remaining-budget arc when budget set) */}
                <circle
                  cx={50} cy={50} r={RADIUS}
                  fill="none"
                  stroke={hasBudget && !overBudget ? BUDGET_REMAINING_COLOR : 'transparent'}
                  strokeWidth={STROKE}
                />
                {(() => {
                  let cumulative = 0;
                  return slices.map((s) => {
                    const dash = (s.value / denom) * C;
                    const offset = -((cumulative / denom) * C);
                    cumulative += s.value;
                    return (
                      <circle
                        key={s.category}
                        cx={50} cy={50} r={RADIUS}
                        fill="none"
                        stroke={s.color}
                        strokeWidth={STROKE}
                        strokeDasharray={`${dash} ${C - dash}`}
                        strokeDashoffset={offset}
                      />
                    );
                  });
                })()}
                {slices.length === 0 && (
                  <circle
                    cx={50} cy={50} r={RADIUS}
                    fill="none"
                    stroke={BUDGET_REMAINING_COLOR}
                    strokeWidth={STROKE}
                  />
                )}
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                <div className={`text-base font-bold ${overBudget ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-white'}`}>
                  {spent.toLocaleString('ru-RU')}
                </div>
                <div className="text-[10px] text-slate-400 leading-tight">
                  {hasBudget ? `из ${totalBudget.toLocaleString('ru-RU')}` : cur}
                </div>
              </div>
            </div>
          </div>

          {/* Summary numbers */}
          {hasBudget ? (
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="text-center px-2 py-1 rounded bg-slate-50 dark:bg-slate-800/40">
                <div className="text-slate-400">Потрачено</div>
                <div className={`font-semibold ${overBudget ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-white'}`}>
                  {spent.toLocaleString('ru-RU')} {cur}
                </div>
              </div>
              <div className="text-center px-2 py-1 rounded bg-slate-50 dark:bg-slate-800/40">
                <div className="text-slate-400">{overBudget ? 'Перерасход' : 'Осталось'}</div>
                <div className={`font-semibold ${overBudget ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                  {Math.abs(remaining).toLocaleString('ru-RU')} {cur}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-xs text-slate-400 text-center">Бюджет не задан</div>
          )}

          {/* Legend */}
          {slices.length > 0 && (
            <div className="space-y-1 text-xs">
              {slices.map((s) => {
                const pct = denom > 0 ? Math.round((s.value / denom) * 100) : 0;
                return (
                  <div key={s.category} className="flex items-center gap-2">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: s.color }}
                    />
                    <span className="flex-1 truncate text-slate-600 dark:text-slate-300">
                      {s.label}
                    </span>
                    <span className="text-slate-400 tabular-nums">{pct}%</span>
                    <span className="text-slate-700 dark:text-slate-200 tabular-nums w-16 text-right">
                      {s.value.toLocaleString('ru-RU')}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {slices.length === 0 && hasBudget && (
            <div className="text-[11px] text-slate-400 text-center">
              Укажите траты у мест в днях, чтобы увидеть разбивку.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
