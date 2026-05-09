import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { api, ApiError, type ChatSummary, type ChatMessage, type StreamCallbacks } from '@/shared/api';
import { useAuth } from '@/modules/auth';
import { ChatSidebar } from './ChatSidebar';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { TypingIndicator } from './TypingIndicator';
import { Heart, Menu, X } from 'lucide-react';

interface DisplayMessage {
  id: string;
  type: 'user' | 'ai';
  content: string;
  showMap?: boolean;
}

export default function ChatPage() {
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [chatId, setChatId] = useState<number | null>(null);
  const [chatList, setChatList] = useState<ChatSummary[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [streamingTool, setStreamingTool] = useState<string | null>(null);
  const [isFavorited, setIsFavorited] = useState(false);
  const [currentTripId, setCurrentTripId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [currentAiMsgId, setCurrentAiMsgId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sendingRef = useRef(false);
  const pendingMapReadyRef = useRef(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, logout } = useAuth();

  useEffect(() => {
    if (!isAuthenticated) navigate('/login');
  }, [isAuthenticated, navigate]);

  const loadChatList = useCallback(async () => {
    try {
      const data = await api.getChats();
      setChatList(data.chats);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        navigate('/login');
      }
    } finally {
      setLoadingHistory(false);
    }
  }, [logout, navigate]);

  useEffect(() => {
    if (isAuthenticated) loadChatList();
  }, [isAuthenticated, loadChatList]);

  const loadChat = useCallback(async (id: number) => {
    setChatId(id);
    setSidebarOpen(false);
    try {
      const data = await api.getChat(id);
      setIsFavorited(data.is_favorited ?? false);
      setCurrentTripId(data.trip?.id ?? null);
      const displayMsgs: DisplayMessage[] = data.messages.map((m: ChatMessage) => ({
        id: String(m.id),
        type: m.role === 'user' ? ('user' as const) : ('ai' as const),
        content: m.content,
      }));
      // Show map button on last AI message if trip has a plan
      const trip = data.trip;
      if (trip && trip.has_plan && displayMsgs.length > 0) {
        const lastAi = [...displayMsgs].reverse().find(m => m.type === 'ai');
        if (lastAi) lastAi.showMap = true;
      }
      setMessages(displayMsgs);
    } catch {
      setMessages([]);
    }
  }, []);

  const startNewChat = useCallback(() => {
    setChatId(null);
    setIsFavorited(false);
    setCurrentTripId(null);
    setSidebarOpen(false);
    setMessages([
      {
        id: 'welcome',
        type: 'ai',
        content:
          'Привет! Я Odyssey AI — твой персональный тревел-ассистент. Расскажи, куда хочешь поехать?',
      },
    ]);
  }, []);

  useEffect(() => {
    startNewChat();
  }, [startNewChat]);

  // Open specific chat if navigated from favorites (state.chatId)
  // or from TripBuilderPage "Спросить ИИ" (?chat=<id>).
  useEffect(() => {
    const state = location.state as { chatId?: number } | null;
    if (state?.chatId) {
      loadChat(state.chatId);
      window.history.replaceState({}, '');
      return;
    }
    const params = new URLSearchParams(location.search);
    const qsChat = params.get('chat');
    if (qsChat) {
      const id = Number(qsChat);
      if (Number.isFinite(id) && id > 0) {
        loadChat(id);
        // Clean URL so refresh stays on the chat without re-triggering.
        navigate('/chat', { replace: true });
      }
    }
  }, [location.state, location.search, loadChat, navigate]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSend = async () => {
    if (!inputValue.trim() || isTyping || sendingRef.current) return;
    const text = inputValue.trim();
    sendingRef.current = true;
    pendingMapReadyRef.current = false;
    setInputValue('');

    const userMsg: DisplayMessage = { id: `user-${Date.now()}`, type: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setIsTyping(true);

    const aiMsgId = `ai-${Date.now()}`;
    setMessages((prev) => [...prev, { id: aiMsgId, type: 'ai', content: '' }]);
    setCurrentAiMsgId(aiMsgId);

    const callbacks: StreamCallbacks = {
      onChatCreated: (newChatId) => {
        setChatId(newChatId);
      },
      onToken: (content) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === aiMsgId ? { ...m, content: m.content + content } : m,
          ),
        );
      },
      onTitle: (title, titleChatId) => {
        setChatList((prev) =>
          prev.map((c) => (c.id === titleChatId ? { ...c, title } : c)),
        );
      },
      onToolStart: (tool) => {
        setStreamingTool(tool);
      },
      onToolEnd: () => {
        setStreamingTool(null);
      },
      onMapReady: () => {
        pendingMapReadyRef.current = true;
      },
      onDone: () => {
        const shouldShowMap = pendingMapReadyRef.current;
        pendingMapReadyRef.current = false;
        if (shouldShowMap) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === aiMsgId ? { ...m, showMap: true } : m,
            ),
          );
        }
        sendingRef.current = false;
        setIsTyping(false);
        setStreamingTool(null);
        setCurrentAiMsgId(null);
        abortRef.current = null;
        loadChatList();
      },
      onError: (err) => {
        pendingMapReadyRef.current = false;
        sendingRef.current = false;
        setIsTyping(false);
        setStreamingTool(null);
        abortRef.current = null;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === aiMsgId
              ? {
                  ...m,
                  content:
                    err instanceof ApiError && err.status === 401
                      ? 'Сессия истекла. Пожалуйста, войдите заново.'
                      : 'Произошла ошибка. Попробуйте ещё раз.',
                }
              : m,
          ),
        );
        if (err instanceof ApiError && err.status === 401) {
          logout();
          navigate('/login');
        }
      },
    };

    if (chatId) {
      abortRef.current = api.streamMessage(chatId, text, callbacks);
    } else {
      abortRef.current = api.streamNewChat(text, callbacks);
    }
  };

  const handleDeleteChat = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.deleteChat(id);
      setChatList((prev) => prev.filter((c) => c.id !== id));
      if (chatId === id) startNewChat();
    } catch { /* ignore */ }
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const toggleFavorite = async () => {
    if (!currentTripId) return;
    try {
      if (isFavorited) {
        await api.removeFavorite(currentTripId);
        setIsFavorited(false);
      } else {
        await api.addFavorite(currentTripId);
        setIsFavorited(true);
      }
    } catch { /* ignore */ }
  };

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-black overflow-hidden relative">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" onClick={() => setSidebarOpen(false)}>
          <div className="absolute inset-0 bg-black/50" />
          <div className="relative w-80 h-full" onClick={(e) => e.stopPropagation()}>
            <ChatSidebar
              chatList={chatList}
              activeChatId={chatId}
              loading={loadingHistory}
              onSelectChat={loadChat}
              onNewChat={startNewChat}
              onDeleteChat={handleDeleteChat}
              onLogout={handleLogout}
            />
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <div className="hidden lg:block">
        <ChatSidebar
          chatList={chatList}
          activeChatId={chatId}
          loading={loadingHistory}
          onSelectChat={loadChat}
          onNewChat={startNewChat}
          onDeleteChat={handleDeleteChat}
          onLogout={handleLogout}
        />
      </div>

      <main className="flex-1 flex flex-col w-full h-full min-h-0">
        {/* Chat header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0A0A0A]">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
          >
            <Menu size={20} />
          </button>
          <div className="flex-1 text-center text-sm font-medium text-slate-700 dark:text-slate-300 truncate px-4">
            {chatId ? chatList.find((c) => c.id === chatId)?.title || 'Чат' : 'Новый чат'}
          </div>
          {chatId && currentTripId ? (
            <button
              onClick={toggleFavorite}
              className={`p-2 rounded-lg transition-colors ${
                isFavorited
                  ? 'text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10'
                  : 'text-slate-400 hover:text-red-500 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
              title={isFavorited ? 'Убрать из избранного' : 'Добавить в избранное'}
            >
              <Heart size={20} fill={isFavorited ? 'currentColor' : 'none'} />
            </button>
          ) : (
            <div className="w-9" />
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} type={msg.type} content={msg.content} showMap={msg.showMap} chatId={chatId} />
            ))}
            {isTyping && streamingTool && (
              <div className="text-sm text-slate-500 dark:text-slate-400 italic px-4">
                🔧 Использую инструмент: {streamingTool}...
              </div>
            )}
            {isTyping && !messages.find((m) => m.id.startsWith('ai-') && m.content === '' && messages.indexOf(m) === messages.length - 1) && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <ChatInput
          value={inputValue}
          onChange={setInputValue}
          onSend={handleSend}
          disabled={isTyping}
          quickActions={chatId ? [
            {
              label: '🔄 Перепланировать день',
              onClick: () => {
                const now = new Date();
                const hhmm = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
                setInputValue(
                  `Сейчас ${hhmm}. Перепланируй оставшуюся часть сегодняшнего дня с учётом погоды и того, что ещё открыто.`,
                );
              },
            },
          ] : []}
        />
      </main>
    </div>
  );
}
