export interface UserProfile {
  activity_level: string;
  budget_level: string;
  category_preferences: Record<string, number>;
  landscape_preferences: Record<string, number>;
  food_preferences: Record<string, boolean>;
  start_hour: number;
  meal_count_per_day: number;
}

export interface ChatSummary {
  id: number;
  title: string;
  status: string;
  trip_id: number | null;
  trip: TripSummary | null;
  created_at: string;
  updated_at: string;
  is_favorited: boolean;
}

export interface TripSummary {
  id: number;
  destination: string | null;
  start_date: string | null;
  end_date: string | null;
  has_plan: boolean;
}

export interface ChatMessage {
  id: number;
  role: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ChatWithMessages extends ChatSummary {
  messages: ChatMessage[];
}

export interface ChatListResponse {
  chats: ChatSummary[];
  total: number;
}

export interface AgentReply {
  reply: string;
  chat_id: number;
  chat_title: string;
  metadata: Record<string, unknown>;
}

export interface FavoriteItem {
  id: number;
  chat_id: number;
  chat_title: string;
  custom_name: string | null;
  destination: string | null;
  created_at: string;
}

export interface FavoriteListResponse {
  favorites: FavoriteItem[];
  total: number;
}

export interface TripItem {
  id: number;
  user_id: number;
  name: string;
  start_date: string | null;
  end_date: string | null;
  trip_profile: Record<string, unknown>;
  generated_plan: Record<string, unknown>;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface StreamCallbacks {
  onToken?: (content: string) => void;
  onTitle?: (title: string, chatId: number) => void;
  onChatCreated?: (chatId: number) => void;
  onToolStart?: (tool: string) => void;
  onToolEnd?: (tool: string) => void;
  onMapReady?: (chatId: number) => void;
  onDone?: (reply: string, chatId: number) => void;
  onError?: (error: Error) => void;
}
