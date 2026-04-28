import type {
  TokenResponse,
  UserProfile,
  ChatListResponse,
  ChatWithMessages,
  ChatSummary,
  AgentReply,
  FavoriteListResponse,
  FavoriteItem,
  TripItem,
  StreamCallbacks,
} from './types';

const API_BASE = '/api/v1';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('odyssey_token');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('odyssey_token', token);
    } else {
      localStorage.removeItem('odyssey_token');
    }
  }

  getToken(): string | null {
    return this.token;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    isForm = false,
  ): Promise<T> {
    const headers: Record<string, string> = {};
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    let requestBody: string | URLSearchParams | undefined;
    if (isForm && body) {
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
      requestBody = body as unknown as URLSearchParams;
    } else if (body) {
      headers['Content-Type'] = 'application/json';
      requestBody = JSON.stringify(body);
    }

    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: requestBody as BodyInit | undefined,
    });

    if (res.status === 204) return undefined as T;

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new ApiError(res.status, errData.detail || res.statusText);
    }

    return res.json();
  }

  // ── Auth ──────────────────────────────────────────────
  async register(email: string, password: string, name?: string) {
    return this.request<TokenResponse>(
      'POST', '/auth/register',
      { email, password, full_name: name },
    );
  }

  async login(email: string, password: string) {
    const form = new URLSearchParams();
    form.append('username', email);
    form.append('password', password);
    return this.request<TokenResponse>('POST', '/auth/login', form, true);
  }

  async getYandexAuthUrl() {
    return this.request<{ authorization_url: string }>('GET', '/auth/yandex/login');
  }

  async yandexCallback(code: string) {
    return this.request<TokenResponse>('POST', `/auth/yandex/callback?code=${encodeURIComponent(code)}`);
  }

  // ── Profile ───────────────────────────────────────────
  async hasProfile(): Promise<boolean> {
    const data = await this.request<{ has_profile: boolean }>('GET', '/users/me/profile/status');
    return data.has_profile;
  }

  async getProfile() {
    return this.request<UserProfile>('GET', '/users/me/profile');
  }

  async createProfile(data: Partial<UserProfile>) {
    return this.request<UserProfile>('POST', '/users/me/profile', data);
  }

  async updateProfile(data: Partial<UserProfile>) {
    return this.request<UserProfile>('PUT', '/users/me/profile', data);
  }

  // ── Chats ─────────────────────────────────────────────
  async createChat(message?: string) {
    return this.request<AgentReply>('POST', '/chats', message ? { message } : {});
  }

  async getChats() {
    return this.request<ChatListResponse>('GET', '/chats');
  }

  async getChat(chatId: number) {
    return this.request<ChatWithMessages>('GET', `/chats/${chatId}`);
  }

  async getRouteMap(chatId: number, refresh: boolean = false): Promise<string> {
    const headers: Record<string, string> = {};
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    const qs = refresh ? `?refresh=1&_=${Date.now()}` : `?_=${Date.now()}`;
    const res = await fetch(`${API_BASE}/chats/${chatId}/route-map${qs}`, { headers, cache: 'no-store' });
    if (!res.ok) throw new ApiError(res.status, 'Failed to load map');
    return res.text();
  }

  async sendMessage(chatId: number, message: string) {
    return this.request<AgentReply>('POST', `/chats/${chatId}/messages`, { message });
  }

  streamNewChat(
    message: string,
    callbacks: StreamCallbacks,
  ): AbortController {
    return this._streamSSE('POST', '/chats/stream', { message }, callbacks);
  }

  streamMessage(
    chatId: number,
    message: string,
    callbacks: StreamCallbacks,
  ): AbortController {
    return this._streamSSE('POST', `/chats/${chatId}/stream`, { message }, callbacks);
  }

  private _streamSSE(
    method: string,
    path: string,
    body: unknown,
    callbacks: StreamCallbacks,
  ): AbortController {
    const controller = new AbortController();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.token) headers['Authorization'] = `Bearer ${this.token}`;

    fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          callbacks.onError?.(new ApiError(res.status, err.detail || res.statusText));
          return;
        }
        const reader = res.body?.getReader();
        if (!reader) return;
        const decoder = new TextDecoder();
        let buffer = '';
        let sawDone = false;

        const handleSseBlock = (block: string) => {
          const lines = block.split('\n');
          let currentEvent = '';
          for (const rawLine of lines) {
            const line = rawLine.replace(/\r$/, '');
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                switch (currentEvent) {
                  case 'chat_created':
                    callbacks.onChatCreated?.(parsed.chat_id);
                    break;
                  case 'token':
                    callbacks.onToken?.(parsed.content);
                    break;
                  case 'title':
                    callbacks.onTitle?.(parsed.title, parsed.chat_id);
                    break;
                  case 'tool_start':
                    callbacks.onToolStart?.(parsed.tool);
                    break;
                  case 'tool_end':
                    callbacks.onToolEnd?.(parsed.tool);
                    break;
                  case 'map_ready':
                    callbacks.onMapReady?.(parsed.chat_id);
                    break;
                  case 'done':
                    sawDone = true;
                    callbacks.onDone?.(parsed.reply, parsed.chat_id);
                    break;
                  case 'error':
                    callbacks.onError?.(new Error(parsed.error));
                    break;
                }
              } catch {
                /* skip malformed JSON */
              }
              currentEvent = '';
            }
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            const tail = buffer + decoder.decode();
            const blocks = tail.split('\n\n').filter(Boolean);
            blocks.forEach(handleSseBlock);
            if (!sawDone) {
              callbacks.onDone?.('', -1);
            }
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop() || '';
          blocks.forEach(handleSseBlock);
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          callbacks.onError?.(err);
        }
      });

    return controller;
  }

  async updateChat(chatId: number, title: string) {
    return this.request<ChatSummary>('PATCH', `/chats/${chatId}`, { title });
  }

  async deleteChat(chatId: number) {
    return this.request<void>('DELETE', `/chats/${chatId}`);
  }

  // ── Favorites ─────────────────────────────────────────
  async getFavorites() {
    return this.request<FavoriteListResponse>('GET', '/favorites');
  }

  async addFavorite(chatId: number, customName?: string) {
    return this.request<FavoriteItem>(
      'POST', '/favorites',
      { chat_id: chatId, custom_name: customName },
    );
  }

  async updateFavorite(chatId: number, customName: string) {
    return this.request<FavoriteItem>(
      'PATCH', `/favorites/${chatId}`,
      { custom_name: customName },
    );
  }

  async removeFavorite(chatId: number) {
    return this.request<void>('DELETE', `/favorites/${chatId}`);
  }

  // ── Trips ─────────────────────────────────────────────
  async getTrips() {
    return this.request<TripItem[]>('GET', '/trips/');
  }

  async getTrip(tripId: number) {
    return this.request<TripItem>('GET', `/trips/${tripId}`);
  }

  async replanTripDay(
    tripId: number,
    dayNumber: number,
    body?: { current_datetime_iso?: string; visited_place_names?: string[] },
  ) {
    return this.request<TripItem>(
      'POST',
      `/trips/${tripId}/days/${dayNumber}/replan`,
      body ?? {},
    );
  }
}

export const api = new ApiClient();
