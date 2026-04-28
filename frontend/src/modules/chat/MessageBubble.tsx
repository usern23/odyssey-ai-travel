import { motion } from 'motion/react';
import { Sparkles, User, Map } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useEffect, useState } from 'react';
import { api } from '../../shared/api/client';

interface MessageBubbleProps {
  type: 'user' | 'ai';
  content: string;
  showMap?: boolean;
  chatId?: number | null;
}

function RouteMap({ chatId }: { chatId: number }) {
  const [expanded, setExpanded] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  return (
    <div className="mt-3">
      <div className="flex items-center gap-2">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-950/60 transition-colors text-sm font-medium"
        >
          <Map size={16} />
          {expanded ? 'Скрыть карту' : 'Показать карту маршрута'}
        </button>
        {expanded && (
          <button
            onClick={() => setReloadKey((k) => k + 1)}
            className="px-3 py-2 rounded-xl text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            title="Пересобрать карту"
          >
            ↻ Обновить
          </button>
        )}
      </div>
      {expanded && (
        <MapIframe key={reloadKey} chatId={chatId} forceRefresh={reloadKey > 0} />
      )}
    </div>
  );
}

function MapIframe({ chatId, forceRefresh }: { chatId: number; forceRefresh?: boolean }) {
  const [html, setHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getRouteMap(chatId, !!forceRefresh)
      .then((text) => {
        if (!cancelled) {
          setHtml(text);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [chatId, forceRefresh]);

  if (loading) {
    return (
      <div className="w-full rounded-xl border border-slate-200 dark:border-slate-700 mt-2 flex items-center justify-center bg-slate-50 dark:bg-slate-900" style={{ height: '70vh', minHeight: '500px' }}>
        <span className="text-slate-400">Загрузка карты...</span>
      </div>
    );
  }

  if (error || !html) {
    return (
      <div className="w-full rounded-xl border border-red-200 dark:border-red-800 mt-2 p-4 text-red-500 text-sm">
        Не удалось загрузить карту. Попробуйте позже.
      </div>
    );
  }

  return (
    <iframe
      srcDoc={html}
      className="w-full rounded-xl border border-slate-200 dark:border-slate-700 mt-2"
      style={{ height: '70vh', minHeight: '500px' }}
      sandbox="allow-scripts allow-same-origin"
      title="Route map"
    />
  );
}

export function MessageBubble({ type, content, showMap, chatId }: MessageBubbleProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex gap-4 ${type === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
    >
      <div
        className={`w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm ${
          type === 'ai'
            ? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white'
            : 'bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
        }`}
      >
        {type === 'ai' ? <Sparkles size={18} /> : <User size={18} />}
      </div>

      <div
        className={`flex flex-col gap-3 max-w-[85%] sm:max-w-[75%] ${
          type === 'user' ? 'items-end' : 'items-start'
        }`}
      >
        <div
          className={`px-5 py-3.5 rounded-2xl text-[15px] leading-relaxed shadow-sm ${
            type === 'user'
              ? 'bg-blue-600 text-white rounded-tr-sm whitespace-pre-wrap'
              : 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 rounded-tl-sm prose prose-sm dark:prose-invert max-w-none prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-headings:my-2.5 prose-headings:font-semibold prose-h3:text-base prose-pre:bg-slate-100 prose-pre:dark:bg-slate-800 prose-pre:rounded-lg prose-code:text-blue-600 prose-code:dark:text-blue-400 prose-a:text-blue-600 prose-a:dark:text-blue-400 prose-blockquote:border-l-blue-400 prose-blockquote:bg-blue-50 prose-blockquote:dark:bg-blue-950/30 prose-blockquote:rounded-r-lg prose-blockquote:py-0.5 prose-blockquote:px-3 prose-blockquote:not-italic prose-blockquote:text-slate-600 prose-blockquote:dark:text-slate-400 prose-strong:text-slate-900 prose-strong:dark:text-white prose-hr:my-3'
          }`}
        >
          {type === 'ai' ? <ReactMarkdown>{content}</ReactMarkdown> : content}
        </div>
        {type === 'ai' && showMap && chatId && <RouteMap chatId={chatId} />}
      </div>
    </motion.div>
  );
}
