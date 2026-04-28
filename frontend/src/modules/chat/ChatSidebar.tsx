import { Plus, Clock, Trash2, LogOut, UserCog, Heart, MapPin } from 'lucide-react';
import { useNavigate } from 'react-router';
import type { ChatSummary } from '@/shared/api';

interface ChatSidebarProps {
  chatList: ChatSummary[];
  activeChatId: number | null;
  loading: boolean;
  onSelectChat: (id: number) => void;
  onNewChat: () => void;
  onDeleteChat: (id: number, e: React.MouseEvent) => void;
  onLogout: () => void;
}

export function ChatSidebar({
  chatList,
  activeChatId,
  loading,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onLogout,
}: ChatSidebarProps) {
  const navigate = useNavigate();

  return (
    <aside className="w-80 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0A0A0A] flex flex-col h-full">
      {/* New chat button */}
      <div className="p-4 border-b border-slate-200 dark:border-slate-800">
        <button
          className="w-full flex items-center justify-center gap-2 py-3 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-sm"
          onClick={onNewChat}
        >
          <Plus size={18} /> Новый чат
        </button>
      </div>

      {/* History */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-3">
          История
        </div>

        {loading ? (
          <div className="text-sm text-slate-400 text-center py-4">Загрузка...</div>
        ) : chatList.length === 0 ? (
          <div className="text-sm text-slate-400 text-center py-4">Нет чатов</div>
        ) : (
          <div className="space-y-1">
            {chatList.map((chat) => (
              <button
                key={chat.id}
                onClick={() => onSelectChat(chat.id)}
                className={`w-full flex items-center gap-3 px-3 py-3 rounded-xl text-sm transition-colors text-left group ${
                  activeChatId === chat.id
                    ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300'
                    : 'hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300'
                }`}
              >
                <Clock size={16} className="text-slate-400 shrink-0" />
                <span className="truncate flex-1">{chat.title}</span>
                <button
                  onClick={(e) => onDeleteChat(chat.id, e)}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-500 transition-all shrink-0"
                >
                  <Trash2 size={14} />
                </button>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Navigation & Profile & Logout */}
      <div className="p-4 border-t border-slate-200 dark:border-slate-800 space-y-1">
        <button
          onClick={() => navigate('/trips')}
          className="w-full flex items-center justify-center gap-2 py-2.5 text-sm text-slate-600 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-xl transition-colors"
        >
          <MapPin size={16} /> Мои поездки
        </button>
        <button
          onClick={() => navigate('/favorites')}
          className="w-full flex items-center justify-center gap-2 py-2.5 text-sm text-slate-600 dark:text-slate-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-xl transition-colors"
        >
          <Heart size={16} /> Сохраненное
        </button>
        <button
          onClick={() => navigate('/questionnaire?edit=true')}
          className="w-full flex items-center justify-center gap-2 py-2.5 text-sm text-slate-600 dark:text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-xl transition-colors"
        >
          <UserCog size={16} /> Мой профиль
        </button>
        <button
          onClick={onLogout}
          className="w-full flex items-center justify-center gap-2 py-2.5 text-sm text-slate-600 dark:text-slate-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-xl transition-colors"
        >
          <LogOut size={16} /> Выйти
        </button>
      </div>
    </aside>
  );
}
