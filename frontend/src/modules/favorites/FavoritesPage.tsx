import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { Heart, Search } from 'lucide-react';
import { api, ApiError, type FavoriteItem } from '@/shared/api';
import { useAuth } from '@/modules/auth';
import { FavoriteCard } from './FavoriteCard';

export default function FavoritesPage() {
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const navigate = useNavigate();
  const { isAuthenticated, logout } = useAuth();

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login');
      return;
    }
    loadFavorites();
  }, [isAuthenticated, navigate]);

  const loadFavorites = async () => {
    try {
      const data = await api.getFavorites();
      setFavorites(data.favorites);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        navigate('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (chatId: number) => {
    try {
      await api.removeFavorite(chatId);
      setFavorites((prev) => prev.filter((f) => f.chat_id !== chatId));
    } catch { /* ignore */ }
  };

  const filtered = searchQuery
    ? favorites.filter(
        (f) =>
          f.chat_title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          f.destination?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          f.custom_name?.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : favorites;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black pt-10 pb-20 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-10">
          <div>
            <h1 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white mb-2">
              Сохраненные маршруты
            </h1>
            <p className="text-slate-600 dark:text-slate-400">
              Ваша персональная коллекция идей для путешествий.
            </p>
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type="text"
              placeholder="Поиск..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 shadow-sm w-full md:w-64 text-slate-900 dark:text-white"
            />
          </div>
        </div>

        {/* Grid */}
        {loading ? (
          <div className="text-center py-20 text-slate-400">Загрузка...</div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-20">
            <Heart size={48} className="mx-auto mb-4 text-slate-300 dark:text-slate-600" />
            <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-300 mb-2">
              {favorites.length === 0 ? 'Нет сохранённых маршрутов' : 'Ничего не найдено'}
            </h3>
            <p className="text-slate-500 dark:text-slate-400 text-sm">
              {favorites.length === 0
                ? 'Добавляйте чаты в избранное, чтобы они появились здесь.'
                : 'Попробуйте другой запрос.'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {filtered.map((item, i) => (
              <FavoriteCard key={item.id} item={item} index={i} onRemove={handleRemove} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
