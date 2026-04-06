import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { api, ApiError } from '@/shared/api';

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  loginWithYandex: () => Promise<void>;
  handleYandexCallback: (code: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: !!api.getToken(),
    isLoading: false,
  });

  useEffect(() => {
    if (api.getToken()) {
      api.getChats().catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          api.setToken(null);
          setState({ isAuthenticated: false, isLoading: false });
        }
      });
    }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setState((s) => ({ ...s, isLoading: true }));
    try {
      const { access_token } = await api.login(email, password);
      api.setToken(access_token);
      setState({ isAuthenticated: true, isLoading: false });
    } catch (err) {
      setState((s) => ({ ...s, isLoading: false }));
      throw err;
    }
  }, []);

  const register = useCallback(
    async (email: string, password: string, name?: string) => {
      setState((s) => ({ ...s, isLoading: true }));
      try {
        const { access_token } = await api.register(email, password, name);
        api.setToken(access_token);
        setState({ isAuthenticated: true, isLoading: false });
      } catch (err) {
        setState((s) => ({ ...s, isLoading: false }));
        throw err;
      }
    },
    [],
  );

  const loginWithYandex = useCallback(async () => {
    const { authorization_url } = await api.getYandexAuthUrl();
    window.location.href = authorization_url;
  }, []);

  const handleYandexCallback = useCallback(async (code: string) => {
    setState((s) => ({ ...s, isLoading: true }));
    try {
      const { access_token } = await api.yandexCallback(code);
      api.setToken(access_token);
      setState({ isAuthenticated: true, isLoading: false });
    } catch (err) {
      setState((s) => ({ ...s, isLoading: false }));
      throw err;
    }
  }, []);

  const logout = useCallback(() => {
    api.setToken(null);
    setState({ isAuthenticated: false, isLoading: false });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, register, loginWithYandex, handleYandexCallback, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
