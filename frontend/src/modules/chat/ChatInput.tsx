import { Send } from 'lucide-react';

export interface QuickAction {
  label: string;
  onClick: () => void;
}

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled: boolean;
  quickActions?: QuickAction[];
}

export function ChatInput({ value, onChange, onSend, disabled, quickActions }: ChatInputProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="shrink-0 p-4 sm:p-6 bg-slate-50 dark:bg-black border-t border-slate-200/50 dark:border-slate-800/50">
      <div className="max-w-3xl mx-auto">
        {quickActions && quickActions.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {quickActions.map((action, idx) => (
              <button
                key={idx}
                onClick={action.onClick}
                disabled={disabled}
                className="px-3 py-1.5 text-xs rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-blue-50 dark:hover:bg-slate-800 hover:border-blue-300 dark:hover:border-blue-700 transition-colors disabled:opacity-50"
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
        <div className="relative bg-white dark:bg-slate-900 rounded-2xl shadow-lg shadow-slate-200/50 dark:shadow-none border border-slate-200 dark:border-slate-700 flex items-end overflow-hidden focus-within:ring-2 focus-within:ring-blue-500/20 focus-within:border-blue-500 transition-all">
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Расскажите о путешествии вашей мечты..."
            className="w-full max-h-32 min-h-[60px] py-4 pl-4 pr-14 resize-none outline-none text-[15px] bg-transparent text-slate-800 dark:text-slate-200 placeholder:text-slate-400"
            rows={1}
          />
          <button
            onClick={onSend}
            disabled={!value.trim() || disabled}
            className="absolute right-2 bottom-2 p-2.5 rounded-xl bg-blue-600 text-white disabled:bg-slate-100 dark:disabled:bg-slate-800 disabled:text-slate-400 hover:bg-blue-700 transition-colors"
          >
            <Send
              size={18}
              className={value.trim() ? 'translate-x-0.5 -translate-y-0.5' : ''}
            />
          </button>
        </div>
        <div className="text-center mt-3 text-xs text-slate-400 dark:text-slate-500">
          AI может ошибаться. Проверяйте важную информацию о путешествиях.
        </div>
      </div>
    </div>
  );
}
