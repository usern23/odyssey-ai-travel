import { motion } from 'motion/react';
import { useNavigate } from 'react-router';
import { MapPin, Calendar, Trash2 } from 'lucide-react';
import type { FavoriteItem } from '@/shared/api';

interface FavoriteCardProps {
  item: FavoriteItem;
  index: number;
  onRemove: (chatId: number) => void;
}

export function FavoriteCard({ item, index, onRemove }: FavoriteCardProps) {
  const navigate = useNavigate();

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.1 }}
      className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-xl dark:hover:shadow-blue-900/10 transition-all group flex flex-col cursor-pointer"
      onClick={() => navigate('/chat')}
    >
      <div className="relative bg-gradient-to-br from-blue-500 to-indigo-600 aspect-[4/3] flex items-center justify-center">
        <MapPin size={48} className="text-white/40" />
        <div className="absolute top-3 right-3">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemove(item.chat_id);
            }}
            className="p-2 bg-white/90 dark:bg-black/50 backdrop-blur text-red-500 rounded-full hover:scale-110 transition-all shadow-sm"
          >
            <Trash2 size={18} />
          </button>
        </div>
        {item.destination && (
          <div className="absolute top-3 left-3">
            <span className="px-2.5 py-1 bg-black/60 backdrop-blur-md text-white text-xs font-medium rounded-lg">
              {item.destination}
            </span>
          </div>
        )}
      </div>

      <div className="p-5 flex flex-col flex-1">
        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2 leading-snug group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
          {item.custom_name || item.chat_title}
        </h3>

        <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
            <Calendar size={16} className="text-slate-400" />
            {new Date(item.created_at).toLocaleDateString('ru-RU')}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
