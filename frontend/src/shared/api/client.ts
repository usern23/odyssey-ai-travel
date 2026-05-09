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
  PlanPlace,
  CreateManualTripPayload,
  AskAiResult,
} from './types';

const API_BASE = '/api/v1';

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail ?? message;
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
      const rawDetail = errData.detail;
      const message = typeof rawDetail === 'string'
        ? rawDetail
        : (rawDetail && typeof rawDetail === 'object' && 'message' in rawDetail
            ? String((rawDetail as Record<string, unknown>).message)
            : res.statusText);
      throw new ApiError(res.status, message, rawDetail);
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

  async addFavorite(tripId: number, customName?: string) {
    return this.request<FavoriteItem>(
      'POST', '/favorites',
      { trip_id: tripId, custom_name: customName },
    );
  }

  async updateFavorite(tripId: number, customName: string) {
    return this.request<FavoriteItem>(
      'PATCH', `/favorites/${tripId}`,
      { custom_name: customName },
    );
  }

  async removeFavorite(tripId: number) {
    return this.request<void>('DELETE', `/favorites/${tripId}`);
  }

  // ── Trips ─────────────────────────────────────────────
  async getTrips() {
    return this.request<TripItem[]>('GET', '/trips/');
  }

  async getTrip(tripId: number) {
    return this.request<TripItem>('GET', `/trips/${tripId}`);
  }

  async deleteTrip(tripId: number) {
    return this.request<void>('DELETE', `/trips/${tripId}`);
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

  // ── Manual Trip Builder ──────────────────────────────
  async createManualTrip(payload: CreateManualTripPayload) {
    return this.request<TripItem>('POST', '/trips/manual', payload);
  }

  async addPlaceToDay(
    tripId: number,
    dayNumber: number,
    body: {
      place: PlanPlace;
      index?: number | null;
      is_locked?: boolean;
      note?: string | null;
      actual_cost?: number | null;
      expected_version?: number | null;
    },
  ) {
    return this.request<TripItem>(
      'POST', `/trips/${tripId}/days/${dayNumber}/places`, body,
    );
  }

  async updateActivity(
    tripId: number,
    dayNumber: number,
    activityIndex: number,
    body: {
      note?: string | null;
      actual_cost?: number | null;
      is_locked?: boolean | null;
      visit_duration_min?: number | null;
      expected_version?: number | null;
    },
  ) {
    return this.request<TripItem>(
      'PATCH',
      `/trips/${tripId}/days/${dayNumber}/places/${activityIndex}`,
      body,
    );
  }

  async removePlaceFromDay(
    tripId: number,
    dayNumber: number,
    activityIndex: number,
    expectedVersion?: number | null,
  ) {
    const qs = expectedVersion != null
      ? `?expected_version=${expectedVersion}` : '';
    return this.request<TripItem>(
      'DELETE',
      `/trips/${tripId}/days/${dayNumber}/places/${activityIndex}${qs}`,
    );
  }

  async reorderDay(
    tripId: number,
    dayNumber: number,
    body: { new_indices: number[]; expected_version?: number | null },
  ) {
    return this.request<TripItem>(
      'POST', `/trips/${tripId}/days/${dayNumber}/reorder`, body,
    );
  }

  async movePlace(
    tripId: number,
    body: {
      from_day: number;
      to_day: number;
      activity_index: number;
      target_index?: number | null;
      expected_version?: number | null;
    },
  ) {
    return this.request<TripItem>(
      'POST', `/trips/${tripId}/places/move`, body,
    );
  }

  async addToWishlist(
    tripId: number,
    body: { place: PlanPlace; expected_version?: number | null },
  ) {
    return this.request<TripItem>('POST', `/trips/${tripId}/wishlist`, body);
  }

  async removeFromWishlist(
    tripId: number,
    wishlistIndex: number,
    expectedVersion?: number | null,
  ) {
    const qs = expectedVersion != null
      ? `?expected_version=${expectedVersion}` : '';
    return this.request<TripItem>(
      'DELETE', `/trips/${tripId}/wishlist/${wishlistIndex}${qs}`,
    );
  }

  async promoteFromWishlist(
    tripId: number,
    wishlistIndex: number,
    body: {
      day_number: number;
      target_index?: number | null;
      expected_version?: number | null;
    },
  ) {
    return this.request<TripItem>(
      'POST', `/trips/${tripId}/wishlist/${wishlistIndex}/promote`, body,
    );
  }

  async updateBudget(
    tripId: number,
    body: {
      total?: number | null;
      by_category?: Record<string, number> | null;
      currency?: string | null;
      lodging_total?: number | null;
      transport_total?: number | null;
      expected_version?: number | null;
    },
  ) {
    return this.request<TripItem>('PATCH', `/trips/${tripId}/budget`, body);
  }

  async optimizeDay(
    tripId: number,
    dayNumber: number,
    body?: { expected_version?: number | null },
  ) {
    return this.request<TripItem>(
      'POST', `/trips/${tripId}/days/${dayNumber}/optimize`, body ?? {},
    );
  }

  async optimizeDayPreview(
    tripId: number,
    dayNumber: number,
    body?: { expected_version?: number | null },
  ) {
    return this.request<{
      before_count: number;
      after_count: number;
      added: string[];
      removed: string[];
      kept: string[];
      total_distance_km_before: number;
      total_distance_km_after: number;
      total_travel_time_min_before: number;
      total_travel_time_min_after: number;
    }>(
      'POST', `/trips/${tripId}/days/${dayNumber}/optimize/preview`, body ?? {},
    );
  }

  async updateHotel(
    tripId: number,
    body: { hotel: PlanPlace | null; expected_version?: number | null },
  ) {
    return this.request<TripItem>('PATCH', `/trips/${tripId}/hotel`, body);
  }

  async askAiForTrip(tripId: number, initialMessage?: string) {
    return this.request<AskAiResult>(
      'POST', `/trips/${tripId}/ask-ai`,
      { initial_message: initialMessage ?? null },
    );
  }

  async searchPlaces(body: {
    query: string;
    near_lat?: number | null;
    near_lon?: number | null;
    radius_km?: number | null;
    limit?: number;
  }) {
    return this.request<{
      results: Array<{
        name: string;
        lat: number;
        lon: number;
        category: string;
        address?: string | null;
        source?: string | null;
      }>;
      count: number;
    }>('POST', '/places/search', body);
  }
}

export const api = new ApiClient();
