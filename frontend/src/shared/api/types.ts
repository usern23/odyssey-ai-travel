export interface UserProfile {
  activity_level: string;
  budget_level: string;
  category_preferences: Record<string, number>;
  landscape_preferences: Record<string, number>;
  food_preferences: Record<string, boolean>;
  start_hour: number;
  end_hour?: number | null;
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
  trip_id: number;
  trip_name: string;
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

// ════════════════════════════════════════════════════════════════
// Manual Trip Builder — domain shapes
// ════════════════════════════════════════════════════════════════
export interface PlanPlace {
  name: string;
  lat: number;
  lon: number;
  category: string;
  visit_duration_min?: number;
  opening_hours?: string | null;
  description?: string | null;
  address?: string | null;
  rating?: number | null;
  price_level?: number | null;
  source?: string | null;
}

export interface PlanActivity {
  place: PlanPlace;
  start_time: string;
  end_time: string;
  travel_time_from_prev_min: number;
  travel_distance_from_prev_km: number;
  notes?: string | null;
  note?: string | null;
  actual_cost?: number | null;
  is_locked?: boolean;
}

export interface PlanDay {
  day_number: number;
  date: string;
  activities: PlanActivity[];
  route_geometry?: string | null;
  total_distance_km: number;
  total_travel_time_min: number;
  total_visit_time_min: number;
  heading?: string | null;
}

export interface TravelPlanDto {
  destination: string;
  hotel: PlanPlace;
  days: PlanDay[];
  start_date?: string | null;
  end_date?: string | null;
  total_places: number;
  total_distance_km: number;
  total_travel_time_min: number;
  candidates?: PlanPlace[];
  start_hour?: number;
  // Manual-builder fields (back-compat: optional/defaulted server-side)
  version?: number;
  wishlist?: PlanPlace[];
  budget_total?: number | null;
  budget_by_category?: Record<string, number>;
  budget_currency?: string;
  lodging_total?: number | null;
  transport_total?: number | null;
  source?: 'agent' | 'manual' | 'mixed';
  plan_notes?: Array<Record<string, unknown>>;
}

export interface CreateManualTripPayload {
  name: string;
  destination: string;
  origin?: string;
  start_date?: string;
  end_date?: string;
  /** Optional. If omitted, server geocodes `destination` for a placeholder. */
  hotel?: PlanPlace;
  start_hour?: number;
  /** End-of-day cap, 1..24. Defaults to 22 server-side. */
  end_hour?: number;
  trip_profile?: Record<string, unknown>;
}

export interface VersionConflictDetail {
  error: 'version_conflict';
  expected: number;
  actual: number;
  message: string;
}

export interface AskAiResult {
  chat_id: number;
  trip_id: number;
  created: boolean;
  initial_message: string | null;
}
