export type Nullable<T> = T | null | undefined;

export interface MediaAsset {
  label: string;
  source_url?: string;
  proxy_url: string;
  /** A local copy created immediately while the signed CDN URL is still valid. */
  local_proxy_url?: string;
  local_analysis_id?: string;
}

interface TranscriptionSegment {
  start: number;
  end: number;
  text: string;
}

export interface TranscriptionData {
  aweme_id: string;
  text: string;
  segments: TranscriptionSegment[];
  language: string;
  language_probability: number;
  duration_seconds: number;
  model: string;
  punctuation_model?: string;
  device: string;
  compute_type: string;
  source_kind: "audio" | "video";
  cached: boolean;
  elapsed_seconds: number;
}

export interface UserSummary {
  nickname: string;
  unique_id?: string;
  sec_user_id?: string;
  uid?: string;
  signature?: string;
  follower_count?: number;
  following_count?: number;
  aweme_count?: number;
  ip_location?: string;
  live_status?: number;
  avatar?: MediaAsset;
}

export interface AuthorProfile extends UserSummary {
  uid?: string;
  short_id?: string;
  signature?: string;
  avatar_url?: string;
  follower_count?: number;
  following_count?: number;
  total_favorited?: number;
  aweme_count?: number;
  favoriting_count?: number;
  mix_count?: number;
  city?: string;
  country?: string;
  ip_location?: string;
  gender?: number;
  user_age?: number;
  live_status?: number;
  is_ban?: boolean;
}

interface Statistics {
  likes?: number;
  comments?: number;
  shares?: number;
  collects?: number;
  admires?: number;
  plays?: number;
}

interface CommentReply {
  id: string;
  text: string;
  created_at?: string;
  likes?: number;
  ip_label?: string;
  user: UserSummary;
}

export interface CommentItem extends CommentReply {
  reply_total?: number;
  is_hot?: boolean;
  is_author_liked?: boolean;
  label?: string;
  images?: MediaAsset[];
  replies?: CommentReply[];
}

export interface AwemeSummary {
  aweme_id: string;
  description: string;
  created_at?: string;
  duration_ms?: number;
  aweme_type?: number;
  author: Pick<UserSummary, "nickname" | "unique_id">;
  statistics: Statistics;
  cover?: MediaAsset;
  douyin_url?: string;
}

interface MusicInfo {
  id?: string;
  mid?: string;
  title?: string;
  author?: string;
  duration_seconds?: number;
  status?: number;
  is_original?: boolean;
  is_original_sound?: boolean;
  is_commerce_music?: boolean;
  is_pgc?: boolean;
  owner_nickname?: string;
  owner_id?: string;
  audio?: MediaAsset;
  cover?: MediaAsset;
}

interface VideoTechnical {
  format?: string;
  ratio?: string;
  has_watermark?: boolean;
  is_h265?: boolean;
  is_hdr?: boolean;
  is_long_video?: boolean;
  bit_rates?: Array<{
    gear?: string;
    bit_rate?: number;
    format?: string;
    fps?: number;
    codec?: string;
    quality_type?: number;
    data_size?: number;
  }>;
}

export interface InspectorData {
  platform: "douyin" | "tiktok";
  access_mode: "visitor" | "login_cookie";
  aweme_id: string;
  share_url: string;
  description: string;
  caption?: string;
  created_at?: string;
  duration_ms?: number;
  width?: number;
  height?: number;
  author: AuthorProfile;
  statistics: Statistics;
  hashtags?: Array<{ id: string; name: string }>;
  content?: Record<string, unknown>;
  permissions?: Record<string, unknown>;
  status?: Record<string, unknown>;
  music?: MusicInfo;
  mix?: Record<string, unknown>;
  ocr_text?: string;
  video_technical?: VideoTechnical;
  audio?: MediaAsset;
  video?: MediaAsset;
  images: MediaAsset[];
  comments?: {
    total?: number;
    has_more?: boolean;
    items: CommentItem[];
  };
  related?: AwemeSummary[];
  author_posts?: AwemeSummary[];
  supplemental_errors?: Record<string, string>;
  warnings?: string[];
  raw_detail: Record<string, unknown>;
}

export interface UserProfilePayload {
  access_mode: "visitor" | "login_cookie";
  profile: AuthorProfile & {
    profile_url?: string;
    avatar?: MediaAsset;
  };
  posts: AwemeSummary[];
  posts_error?: string;
  pagination: UserPostsPagination;
}

interface UserPostsPagination {
  has_more: boolean;
  next_cursor?: number | null;
}

export interface UserPostsPage {
  access_mode: "visitor" | "login_cookie";
  posts: AwemeSummary[];
  pagination: UserPostsPagination;
}

export interface SessionStatus {
  configured: boolean;
  cookie_count: number;
  has_login_markers: boolean;
  message?: string;
}

interface CursorPagination {
  has_more: boolean;
  next_cursor?: number | null;
}

export interface CapabilityPage<T> {
  access_mode: "visitor" | "login_cookie";
  items: T[];
  pagination?: CursorPagination;
  total?: number;
  search_id?: string;
}

export interface CollectionFolder {
  id: string;
  name: string;
  description?: string;
  count?: number;
  cover?: MediaAsset;
}

export interface CollectedMusic {
  id: string;
  title: string;
  author?: string;
  duration_seconds?: number;
  use_count?: number;
  cover?: MediaAsset;
  audio?: MediaAsset;
}

export interface LiveRoomInfo {
  room_id: string;
  web_rid?: string;
  title?: string;
  status?: number;
  viewer_count?: number | string;
  owner: UserSummary;
  cover?: MediaAsset;
  flv_url?: string | Record<string, string>;
  hls_url?: string | Record<string, string>;
}

export interface LiveRoomPayload {
  access_mode: "visitor" | "login_cookie";
  live: LiveRoomInfo;
}

export interface AccountProfilePayload {
  access_mode: "login_cookie";
  profile: UserSummary;
  raw: Record<string, unknown>;
}
