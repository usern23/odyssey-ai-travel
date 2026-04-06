import { Plane } from 'lucide-react';

export function Footer() {
  return (
    <footer className="border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-black py-8 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center gap-4">
        <div className="flex items-center gap-2 text-slate-900 dark:text-white">
          <Plane size={16} className="text-blue-600 dark:text-blue-500" />
          <span className="font-semibold tracking-tight">Odyssey AI</span>
        </div>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          &copy; 2026 Odyssey AI. Персональные путешествия с помощью ИИ.
        </p>
      </div>
    </footer>
  );
}
