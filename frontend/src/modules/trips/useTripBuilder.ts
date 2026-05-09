import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, type TripItem, type TravelPlanDto, type PlanPlace } from '@/shared/api';

export interface UseTripBuilderResult {
  trip: TripItem | null;
  plan: TravelPlanDto | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  versionConflict: { expected: number; actual: number } | null;
  placeFitError: { place_name: string; reason: string; day_end_hour: number; message: string } | null;
  clearPlaceFitError: () => void;
  reload: () => Promise<void>;
  // Mutations — each refreshes plan from the server response.
  addPlace: (dayNumber: number, place: PlanPlace, index?: number | null,
             extras?: { is_locked?: boolean; note?: string | null; actual_cost?: number | null }) => Promise<void>;
  updateActivity: (dayNumber: number, activityIndex: number,
                   patch: { note?: string | null; actual_cost?: number | null;
                            is_locked?: boolean | null; visit_duration_min?: number | null }) => Promise<void>;
  removeActivity: (dayNumber: number, activityIndex: number) => Promise<void>;
  reorderDay: (dayNumber: number, newIndices: number[]) => Promise<void>;
  movePlace: (fromDay: number, toDay: number, activityIndex: number, targetIndex?: number | null) => Promise<void>;
  addToWishlist: (place: PlanPlace) => Promise<void>;
  removeFromWishlist: (wishlistIndex: number) => Promise<void>;
  promoteFromWishlist: (wishlistIndex: number, dayNumber: number, targetIndex?: number | null) => Promise<void>;
  updateBudget: (patch: { total?: number | null; by_category?: Record<string, number> | null;
                           currency?: string | null;
                           lodging_total?: number | null;
                           transport_total?: number | null }) => Promise<void>;
  optimizeDay: (dayNumber: number) => Promise<void>;
  updateHotel: (hotel: PlanPlace | null) => Promise<void>;
}

function extractPlan(trip: TripItem | null): TravelPlanDto | null {
  if (!trip || !trip.generated_plan) return null;
  const stored = trip.generated_plan as Record<string, unknown>;
  const data = stored.plan_data as TravelPlanDto | undefined;
  return data ?? null;
}

export function useTripBuilder(tripId: number): UseTripBuilderResult {
  const [trip, setTrip] = useState<TripItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [versionConflict, setVersionConflict] = useState<{ expected: number; actual: number } | null>(null);
  const [placeFitError, setPlaceFitError] = useState<{ place_name: string; reason: string; day_end_hour: number; message: string } | null>(null);

  // Re-entrant guard: never run two mutations in parallel — they would
  // race over `expected_version` and produce spurious 409s.
  const mutationLock = useRef(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const t = await api.getTrip(tripId);
      setTrip(t);
      setVersionConflict(null);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Failed to load trip';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [tripId]);

  useEffect(() => { void reload(); }, [reload]);

  const plan = extractPlan(trip);

  const runMutation = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    if (mutationLock.current) return null;
    mutationLock.current = true;
    setSaving(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const detail = e.detail as Record<string, unknown> | string | undefined;
        // PLACE_DOES_NOT_FIT — surface to UI without reloading.
        if (detail && typeof detail === 'object' && (detail as Record<string, unknown>).code === 'PLACE_DOES_NOT_FIT') {
          setPlaceFitError({
            place_name: String((detail as Record<string, unknown>).place_name ?? ''),
            reason: String((detail as Record<string, unknown>).reason ?? 'out_of_day_window'),
            day_end_hour: Number((detail as Record<string, unknown>).day_end_hour ?? 22),
            message: String((detail as Record<string, unknown>).message ?? 'Место не помещается в день'),
          });
        } else {
          // Server message format: detail = { error, expected, actual, message }
          if (detail && typeof detail === 'object' && 'expected' in detail && 'actual' in detail) {
            setVersionConflict({
              expected: Number((detail as Record<string, unknown>).expected),
              actual: Number((detail as Record<string, unknown>).actual),
            });
          } else {
            try {
              const parsed = JSON.parse(e.message);
              if (parsed?.expected != null && parsed?.actual != null) {
                setVersionConflict({ expected: parsed.expected, actual: parsed.actual });
              }
            } catch {
              /* keep generic */
            }
          }
          // Always refresh on conflict so user sees the truth.
          await reload();
        }
      } else if (e instanceof Error) {
        setError(e.message);
      }
      return null;
    } finally {
      mutationLock.current = false;
      setSaving(false);
    }
  }, [reload]);

  const wrap = useCallback(<A extends unknown[]>(
    fn: (version: number | null, ...args: A) => Promise<TripItem>,
  ) => {
    return async (...args: A) => {
      await runMutation(async () => {
        const v = plan?.version ?? null;
        const updated = await fn(v, ...args);
        setTrip(updated);
        return updated;
      });
    };
  }, [plan?.version, runMutation]);

  const addPlace = wrap(async (version, dayNumber: number, place: PlanPlace,
                                index?: number | null,
                                extras?: { is_locked?: boolean; note?: string | null; actual_cost?: number | null }) => {
    return api.addPlaceToDay(tripId, dayNumber, {
      place,
      index: index ?? null,
      is_locked: extras?.is_locked,
      note: extras?.note,
      actual_cost: extras?.actual_cost,
      expected_version: version,
    });
  });

  const updateActivity = wrap(async (version, dayNumber: number, activityIndex: number,
                                      patch: { note?: string | null; actual_cost?: number | null;
                                               is_locked?: boolean | null; visit_duration_min?: number | null }) => {
    return api.updateActivity(tripId, dayNumber, activityIndex, { ...patch, expected_version: version });
  });

  const removeActivity = wrap(async (version, dayNumber: number, activityIndex: number) => {
    return api.removePlaceFromDay(tripId, dayNumber, activityIndex, version);
  });

  const reorderDay = wrap(async (version, dayNumber: number, newIndices: number[]) => {
    return api.reorderDay(tripId, dayNumber, { new_indices: newIndices, expected_version: version });
  });

  const movePlace = wrap(async (version, fromDay: number, toDay: number,
                                 activityIndex: number, targetIndex?: number | null) => {
    return api.movePlace(tripId, {
      from_day: fromDay, to_day: toDay,
      activity_index: activityIndex, target_index: targetIndex ?? null,
      expected_version: version,
    });
  });

  const addToWishlist = wrap(async (version, place: PlanPlace) => {
    return api.addToWishlist(tripId, { place, expected_version: version });
  });

  const removeFromWishlist = wrap(async (version, wishlistIndex: number) => {
    return api.removeFromWishlist(tripId, wishlistIndex, version);
  });

  const promoteFromWishlist = wrap(async (version, wishlistIndex: number,
                                           dayNumber: number, targetIndex?: number | null) => {
    return api.promoteFromWishlist(tripId, wishlistIndex, {
      day_number: dayNumber, target_index: targetIndex ?? null, expected_version: version,
    });
  });

  const updateBudget = wrap(async (version,
                                    patch: { total?: number | null; by_category?: Record<string, number> | null;
                                             currency?: string | null;
                                             lodging_total?: number | null;
                                             transport_total?: number | null }) => {
    return api.updateBudget(tripId, { ...patch, expected_version: version });
  });

  const optimizeDay = wrap(async (version, dayNumber: number) => {
    return api.optimizeDay(tripId, dayNumber, { expected_version: version });
  });

  const updateHotel = wrap(async (version, hotel: PlanPlace | null) => {
    return api.updateHotel(tripId, { hotel, expected_version: version });
  });

  return {
    trip, plan, loading, saving, error, versionConflict,
    placeFitError, clearPlaceFitError: () => setPlaceFitError(null),
    reload,
    addPlace, updateActivity, removeActivity, reorderDay, movePlace,
    addToWishlist, removeFromWishlist, promoteFromWishlist,
    updateBudget, optimizeDay, updateHotel,
  };
}
