import { motion } from 'motion/react';
import { Sparkles, User, Map, Play } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useEffect, useMemo, useState } from 'react';
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
  const youtubeVideos = useMemo(
    () => (type === 'ai' ? extractYouTubeVideos(content) : []),
    [content, type],
  );
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
        {type === 'ai' && youtubeVideos.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full">
            {youtubeVideos.map((v) => (
              <YouTubePreview key={v.id} videoId={v.id} title={v.title} />
            ))}
          </div>
        )}
        {type === 'ai' && showMap && chatId && <RouteMap chatId={chatId} />}
      </div>
    </motion.div>
  );
}

// ====================================================================
// YouTube preview helpers
// ====================================================================

interface YTVideo { id: string; title?: string }

/**
 * Extract unique YouTube videos from markdown / plain text. Recognises:
 *   - youtu.be/<ID>
 *   - youtube.com/watch?v=<ID>
 *   - youtube.com/shorts/<ID>
 *   - youtube.com/embed/<ID>
 * Captures the surrounding [title](url) text when the URL is in a markdown
 * link, so the preview card can show a meaningful caption.
 */
function extractYouTubeVideos(text: string): YTVideo[] {
  const seen = new Set<string>();
  const out: YTVideo[] = [];
  // 1) Markdown links: [title](url) where url is YouTube.
  const mdRe = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;
  let m: RegExpExecArray | null;
  while ((m = mdRe.exec(text)) !== null) {
    const id = parseYouTubeId(m[2]);
    if (id && !seen.has(id)) {
      seen.add(id);
      out.push({ id, title: m[1] });
    }
  }
  // 2) Bare URLs anywhere in the message.
  const bareRe = /(https?:\/\/(?:www\.)?(?:youtube\.com|youtu\.be)\/[\w\-?=&\/.]+)/g;
  while ((m = bareRe.exec(text)) !== null) {
    const id = parseYouTubeId(m[1]);
    if (id && !seen.has(id)) {
      seen.add(id);
      out.push({ id });
    }
  }
  return out;
}

function parseYouTubeId(url: string): string | null {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, '');
    if (host === 'youtu.be') {
      const id = u.pathname.replace(/^\//, '').split('/')[0];
      return /^[\w-]{6,}$/.test(id) ? id : null;
    }
    if (host.endsWith('youtube.com')) {
      const v = u.searchParams.get('v');
      if (v && /^[\w-]{6,}$/.test(v)) return v;
      const parts = u.pathname.split('/').filter(Boolean);
      const idx = parts.findIndex((p) => p === 'shorts' || p === 'embed' || p === 'live');
      if (idx !== -1 && parts[idx + 1]) {
        const id = parts[idx + 1];
        return /^[\w-]{6,}$/.test(id) ? id : null;
      }
    }
  } catch {
    // ignore
  }
  return null;
}

function YouTubePreview({ videoId, title }: { videoId: string; title?: string }) {
  const url = `https://www.youtube.com/watch?v=${videoId}`;
  // hqdefault is reliably available for every public video.
  const thumb = `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="group relative block rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900 hover:border-blue-400 dark:hover:border-blue-500 transition-colors no-underline"
      title={title || 'Open on YouTube'}
    >
      <div className="relative aspect-video bg-black">
        <img
          src={thumb}
          alt={title || 'YouTube video'}
          loading="lazy"
          className="absolute inset-0 w-full h-full object-cover opacity-90 group-hover:opacity-100 transition-opacity"
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-14 h-14 rounded-full bg-red-600/95 text-white flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform">
            <Play size={24} fill="white" className="ml-1" />
          </div>
        </div>
      </div>
      {title && (
        <div className="px-3 py-2 text-xs text-slate-700 dark:text-slate-200 line-clamp-2">
          {title}
        </div>
      )}
    </a>
  );
}
