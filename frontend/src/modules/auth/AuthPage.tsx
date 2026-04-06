import { useState } from 'react';
import { useNavigate } from 'react-router';
import { motion } from 'motion/react';
import { Plane, ArrowLeft } from 'lucide-react';
import { useAuth } from './auth-context';
import { api, ApiError } from '@/shared/api';

export default function AuthPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { login, register, loginWithYandex, isLoading } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (isLogin) {
        await login(email, password);
        const has = await api.hasProfile();
        navigate(has ? '/chat' : '/questionnaire');
      } else {
        await register(email, password, name || undefined);
        navigate('/questionnaire');
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Произошла ошибка. Попробуйте позже.');
      }
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black text-slate-900 dark:text-white flex flex-col items-center justify-center p-4 relative overflow-hidden font-sans transition-colors duration-300">
      {/* Background */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-blue-500/10 dark:bg-blue-600/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-indigo-500/10 dark:bg-indigo-600/10 rounded-full blur-[100px] pointer-events-none" />

      <button
        onClick={() => navigate(-1)}
        className="absolute top-8 left-8 p-2 rounded-full hover:bg-slate-200 dark:hover:bg-[#1A1A1A] transition-colors z-20 flex items-center gap-2 text-sm font-medium text-slate-600 dark:text-[#A5A5A5]"
      >
        <ArrowLeft size={20} /> Назад
      </button>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, type: 'spring', bounce: 0.4 }}
        className="w-full max-w-md bg-white dark:bg-[#121212] border border-slate-200 dark:border-[#1A1A1A] p-8 md:p-10 rounded-[2rem] relative z-10 shadow-2xl shadow-blue-900/5 dark:shadow-none"
      >
        <div className="flex justify-center mb-8">
          <div className="w-12 h-12 bg-blue-600 dark:bg-blue-500 rounded-full flex items-center justify-center text-white shadow-lg shadow-blue-500/20">
            <Plane fill="currentColor" size={24} className="ml-1 mt-1" />
          </div>
        </div>

        <h2 className="text-3xl font-black text-center mb-2 tracking-tight">
          {isLogin ? 'С возвращением' : 'Начать путешествие'}
        </h2>
        <p className="text-center text-slate-500 dark:text-[#A5A5A5] mb-8 text-sm">
          {isLogin
            ? 'Войдите, чтобы продолжить планирование'
            : 'Создайте аккаунт для сохранения маршрутов'}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-300 px-4 py-3 rounded-xl text-sm">
              {error}
            </div>
          )}

          {!isLogin && (
            <input
              type="text"
              placeholder="Имя"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-slate-50 dark:bg-[#1A1A1A] border border-slate-200 dark:border-[#2A2A2A] rounded-2xl px-5 py-4 text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-[#A5A5A5] focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all"
            />
          )}

          <input
            type="email"
            placeholder="Электронная почта"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full bg-slate-50 dark:bg-[#1A1A1A] border border-slate-200 dark:border-[#2A2A2A] rounded-2xl px-5 py-4 text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-[#A5A5A5] focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all"
            required
          />

          <input
            type="password"
            placeholder="Пароль"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full bg-slate-50 dark:bg-[#1A1A1A] border border-slate-200 dark:border-[#2A2A2A] rounded-2xl px-5 py-4 text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-[#A5A5A5] focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all"
            required
            minLength={8}
          />

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-blue-600 dark:bg-blue-500 text-white font-bold py-4 rounded-2xl hover:bg-blue-700 dark:hover:bg-blue-400 active:scale-[0.98] transition-all mt-4 shadow-lg shadow-blue-600/20 disabled:opacity-50"
          >
            {isLoading ? 'Загрузка...' : isLogin ? 'Войти' : 'Создать аккаунт'}
          </button>
        </form>

        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-slate-200 dark:border-[#2A2A2A]" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="bg-white dark:bg-[#121212] px-4 text-slate-400 dark:text-[#A5A5A5]">или</span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => loginWithYandex()}
          disabled={isLoading}
          className="w-full flex items-center justify-center gap-3 bg-[#FC3F1D] text-white font-bold py-4 rounded-2xl hover:bg-[#e0371a] active:scale-[0.98] transition-all shadow-lg shadow-[#FC3F1D]/20 disabled:opacity-50"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M13.32 7.666h-.924c-1.694 0-2.585.858-2.585 2.123 0 1.43.616 2.1 1.881 2.959l1.045.704-3.003 4.548H7.49l2.695-4.07c-1.694-1.21-2.585-2.474-2.585-4.262 0-2.463 1.694-4.174 4.812-4.174H15.5V18h-2.178V7.666z" fill="currentColor"/></svg>
          Войти через Яндекс
        </button>

        <div className="mt-8 text-center text-sm text-slate-500 dark:text-[#A5A5A5]">
          {isLogin ? 'Нет аккаунта? ' : 'Уже есть аккаунт? '}
          <button
            onClick={() => setIsLogin(!isLogin)}
            className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-bold transition-colors"
          >
            {isLogin ? 'Зарегистрироваться' : 'Войти'}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
