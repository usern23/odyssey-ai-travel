import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { api, ApiError, type ChatSummary, type ChatMessage, type StreamCallbacks } from '@/shared/api';
import { useAuth } from '@/modules/auth';
import { ChatSidebar } from './ChatSidebar';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { TypingIndicator } from './TypingIndicator';

interface DisplayMessage {
  id: string;
  type: 'user' | 'ai';
  content: string;
}

export default function ChatPage() {
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [chatId, setChatId] = useState<number | null>(null);
  const [chatList, setChatList] = useState<ChatSummary[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [streamingTool, setStreamingTool] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const navigate = useNavigate();
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
    try {
      const data = await api.getChat(id);
      const displayMsgs: DisplayMessage[] = data.messages.map((m: ChatMessage) => ({
        id: String(m.id),
        type: m.role === 'user' ? ('user' as const) : ('ai' as const),
        content: m.content,
      }));
      setMessages(displayMsgs);
    } catch {
      setMessages([]);
    }
  }, []);

  const startNewChat = useCallback(() => {
    setChatId(null);
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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSend = async () => {
    if (!inputValue.trim() || isTyping) return;
    const text = inputValue.trim();
    setInputValue('');

    const userMsg: DisplayMessage = { id: `user-${Date.now()}`, type: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setIsTyping(true);

    const aiMsgId = `ai-${Date.now()}`;
    setMessages((prev) => [...prev, { id: aiMsgId, type: 'ai', content: '' }]);

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
        loadChatList();
      },
      onToolStart: (tool) => {
        setStreamingTool(tool);
      },
      onToolEnd: () => {
        setStreamingTool(null);
      },
      onDone: () => {
        setIsTyping(false);
        setStreamingTool(null);
        abortRef.current = null;
        loadChatList();
      },
      onError: (err) => {
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

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-black overflow-hidden relative">
      <ChatSidebar
        chatList={chatList}
        activeChatId={chatId}
        loading={loadingHistory}
        onSelectChat={loadChat}
        onNewChat={startNewChat}
        onDeleteChat={handleDeleteChat}
        onLogout={handleLogout}
      />

      <main className="flex-1 flex flex-col w-full h-full min-h-0">
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} type={msg.type} content={msg.content} />
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
        />
      </main>
    </div>
  );
}
