import { motion } from 'motion/react';
import { Sparkles, User } from 'lucide-react';

interface MessageBubbleProps {
  type: 'user' | 'ai';
  content: string;
}

export function MessageBubble({ type, content }: MessageBubbleProps) {
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
          className={`px-5 py-3.5 rounded-2xl text-[15px] leading-relaxed shadow-sm whitespace-pre-wrap ${
            type === 'user'
              ? 'bg-blue-600 text-white rounded-tr-sm'
              : 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 rounded-tl-sm'
          }`}
        >
          {content}
        </div>
      </div>
    </motion.div>
  );
}
