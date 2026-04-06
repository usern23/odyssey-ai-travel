import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { Plane, Loader2 } from 'lucide-react';
import { useAuth } from './auth-context';
import { api } from '@/shared/api';

export default function YandexCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { handleYandexCallback } = useAuth();
  const [error, setError] = useState('');

  useEffect(() => {
    const code = searchParams.get('code');
    if (!code) {
      setError('Код авторизации не получен');
      return;
    }

    handleYandexCallback(code)
      .then(async () => {
        const has = await api.hasProfile();
        navigate(has ? '/chat' : '/questionnaire', { replace: true });
      })
      .catch(() => {
        setError('Ошибка авторизации через Яндекс');
      });
  }, [searchParams, handleYandexCallback, navigate]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black text-slate-900 dark:text-white flex flex-col items-center justify-center p-4 font-sans transition-colors duration-300">
      <div className="w-12 h-12 bg-blue-600 dark:bg-blue-500 rounded-full flex items-center justify-center text-white shadow-lg shadow-blue-500/20 mb-6">
        <Plane fill="currentColor" size={24} className="ml-1 mt-1" />
      </div>
      {error ? (
        <div className="text-center">
          <p className="text-red-500 mb-4">{error}</p>
          <button
            onClick={() => navigate('/login')}
            className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-bold transition-colors"
          >
            Вернуться к входу
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3 text-slate-500 dark:text-[#A5A5A5]">
          <Loader2 className="animate-spin" size={20} />
          <span>Авторизация через Яндекс...</span>
        </div>
      )}
    </div>
  );
}
