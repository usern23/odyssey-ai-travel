import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { MapPin, Calendar, Plane, Plus, Pencil, Trash2 } from 'lucide-react';
import { api, ApiError, type TripItem } from '@/shared/api';
import { useAuth } from '@/modules/auth';
import CreateManualTripDialog from './CreateManualTripDialog';

export default function TripsPage() {
  const [trips, setTrips] = useState<TripItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const navigate = useNavigate();
  const { isAuthenticated, logout } = useAuth();

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login');
      return;
    }
    loadTrips();
  }, [isAuthenticated, navigate]);

  const loadTrips = async () => {
    try {
      const data = await api.getTrips();
      setTrips(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        navigate('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (d: string | null) => {
    if (!d) return null;
    return new Date(d).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
  };

  const hasPlan = (trip: TripItem) => {
    return trip.generated_plan && Object.keys(trip.generated_plan).length > 0;
  };

  const handleDelete = async (trip: TripItem, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Удалить поездку «${trip.name}»? Это действие необратимо.`)) return;
    try {
      await api.deleteTrip(trip.id);
      setTrips((prev) => prev.filter((t) => t.id !== trip.id));
    } catch (err) {
      alert('Не удалось удалить поездку');
      console.error(err);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black pt-10 pb-20 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        <div className="mb-10 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-2">
              Мои поездки
            </h1>
            <p className="text-slate-600 dark:text-slate-400">
              Все ваши запланированные путешествия.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-2 flex-shrink-0">
            <button
              onClick={() => setCreateOpen(true)}
              className="px-4 py-2 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-1.5"
            >
              <Plus size={16} /> Создать вручную
            </button>
            <button
              onClick={() => navigate('/chat')}
              className="px-4 py-2 rounded-xl bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 flex items-center gap-1.5"
            >
              <Plane size={16} /> Спросить ИИ
            </button>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-20 text-slate-400">Загрузка...</div>
        ) : trips.length === 0 ? (
          <div className="text-center py-20">
            <Plane size={48} className="mx-auto mb-4 text-slate-300 dark:text-slate-600" />
            <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-300 mb-2">
              Нет поездок
            </h3>
            <p className="text-slate-500 dark:text-slate-400 text-sm mb-6">
              Начните планирование в чате — поездки появятся здесь автоматически.
            </p>
            <button
              onClick={() => navigate('/chat')}
              className="px-6 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors"
            >
              Начать планирование
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {trips.map((trip) => (
              <div
                key={trip.id}
                onClick={() => navigate(`/trips/${trip.id}`)}
                className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-lg transition-all cursor-pointer"
              >
                <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-6 text-white">
                  <h3 className="text-lg font-bold mb-1">{trip.name}</h3>
                  {trip.start_date && trip.end_date && (
                    <div className="flex items-center gap-1.5 text-sm text-white/80">
                      <Calendar size={14} />
                      {formatDate(trip.start_date)} — {formatDate(trip.end_date)}
                    </div>
                  )}
                </div>
                <div className="p-5 space-y-3">
                  {trip.trip_profile?.budget ? (
                    <div className="text-sm text-slate-600 dark:text-slate-400">
                      Бюджет: <span className="font-medium text-slate-800 dark:text-slate-200">{String(trip.trip_profile.budget)}</span>
                    </div>
                  ) : null}
                  <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800">
                    <span className={`text-xs font-medium px-2 py-1 rounded-md ${
                      hasPlan(trip)
                        ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-400'
                        : 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400'
                    }`}>
                      {hasPlan(trip) ? 'Маршрут готов' : 'Без маршрута'}
                    </span>
                    <div className="flex items-center gap-1">
                    {hasPlan(trip) && (
                      <button
                        onClick={(e) => { e.stopPropagation(); navigate(`/trips/${trip.id}/edit`); }}
                        className="text-xs px-2 py-1 rounded-md text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-1"
                        title="Редактировать вручную"
                      >
                        <Pencil size={12} /> Изменить
                      </button>
                    )}
                    <button
                      onClick={(e) => handleDelete(trip, e)}
                      className="text-xs px-2 py-1 rounded-md text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 flex items-center gap-1"
                      title="Удалить поездку"
                    >
                      <Trash2 size={12} />
                    </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <CreateManualTripDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
