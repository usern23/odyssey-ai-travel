import { Link, useLocation, useNavigate } from 'react-router';
import { Plane, Heart, User, Sun, Moon, Sparkles, LogOut } from 'lucide-react';
import { useState, useEffect } from 'react';
import { useAuth } from '@/modules/auth';

export function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const [isDark, setIsDark] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('odyssey_dark');
      if (saved !== null) return saved === 'true';
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return false;
  });
  const { isAuthenticated, logout } = useAuth();

  useEffect(() => {
    localStorage.setItem('odyssey_dark', String(isDark));
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-200/80 dark:border-slate-800/80 bg-white/80 dark:bg-black/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="bg-blue-600 p-2 rounded-xl text-white shadow-lg shadow-blue-500/20 group-hover:scale-105 transition-transform">
            <Plane size={18} className="rotate-45" />
          </div>
          <span className="font-bold text-xl tracking-tight bg-gradient-to-r from-blue-600 to-indigo-500 bg-clip-text text-transparent dark:from-blue-400 dark:to-indigo-400">
            Odyssey AI
          </span>
        </Link>

        {/* Navigation */}
        <nav className="hidden md:flex items-center gap-8">
          <NavLink to="/" current={location.pathname}>
            Главная
          </NavLink>
          <NavLink to="/chat" current={location.pathname} icon>
            AI Планировщик
          </NavLink>
          <NavLink to="/trips" current={location.pathname}>
            Мои поездки
          </NavLink>
          <NavLink to="/favorites" current={location.pathname}>
            Сохраненное
          </NavLink>
        </nav>

        {/* Actions */}
        <div className="flex items-center gap-3 sm:gap-4">
          <button
            onClick={() => setIsDark(!isDark)}
            className="p-2 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors"
          >
            {isDark ? <Sun size={20} /> : <Moon size={20} />}
          </button>

          <Link
            to="/favorites"
            className="p-2 text-slate-500 dark:text-slate-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-full transition-colors hidden sm:block"
          >
            <Heart size={20} />
          </Link>

          {isAuthenticated ? (
            <button
              onClick={() => { logout(); navigate('/'); }}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-slate-900 dark:bg-white text-white dark:text-black rounded-full hover:bg-slate-800 dark:hover:bg-slate-200 transition-colors shadow-md"
            >
              <LogOut size={16} /> <span className="hidden sm:inline">Выйти</span>
            </button>
          ) : (
            <Link
              to="/login"
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-slate-900 dark:bg-white text-white dark:text-black rounded-full hover:bg-slate-800 dark:hover:bg-slate-200 transition-colors shadow-md"
            >
              <User size={16} /> <span className="hidden sm:inline">Войти</span>
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}

function NavLink({
  to,
  current,
  icon,
  children,
}: {
  to: string;
  current: string;
  icon?: boolean;
  children: React.ReactNode;
}) {
  const active = current === to;
  return (
    <Link
      to={to}
      className={`text-sm font-medium transition-colors flex items-center gap-1.5 ${
        active
          ? 'text-blue-600 dark:text-blue-400'
          : 'text-slate-600 dark:text-slate-300 hover:text-blue-600 dark:hover:text-blue-400'
      }`}
    >
      {icon && <Sparkles size={16} className="text-blue-500" />}
      {children}
    </Link>
  );
}
