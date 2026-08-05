import { apiRequest } from "./client";
import type {
  AccountProfilePayload,
  AwemeSummary,
  CapabilityPage,
  CollectedMusic,
  CollectionFolder,
  CommentItem,
  InspectorData,
  LiveRoomInfo,
  LiveRoomPayload,
  SessionStatus,
  TranscriptionData,
  UserSummary,
  UserProfilePayload,
  UserPostsPage,
} from "../types/douyin";


export const getSessionStatus = () => apiRequest<SessionStatus>(
  "/api/session/status",
  { cache: "no-store" },
  "无法读取 Cookie 状态",
);

export const saveSessionCookie = (cookie: string) => apiRequest<SessionStatus>(
  "/api/session/cookie",
  { method: "POST", body: JSON.stringify({ cookie }) },
  "Cookie 载入失败",
);

export const clearSessionCookie = () => apiRequest<SessionStatus>(
  "/api/session/cookie",
  { method: "DELETE" },
  "Cookie 清除失败",
);

export const resolveAweme = (shareText: string, awemeId?: string) => apiRequest<InspectorData>(
  "/api/resolve",
  {
    method: "POST",
    body: JSON.stringify({
      share_text: shareText,
      ...(awemeId ? { aweme_id: awemeId } : {}),
    }),
  },
  "解析失败",
);

export const transcribeAweme = (awemeId: string, mediaUrl: string, context: string) =>
  apiRequest<TranscriptionData>(
    "/api/transcription",
    {
      method: "POST",
      body: JSON.stringify({ aweme_id: awemeId, media_url: mediaUrl, context }),
    },
    "文案生成失败",
  );

export const getUserProfile = (secUserId: string) => apiRequest<UserProfilePayload>(
  "/api/user-profile",
  { method: "POST", body: JSON.stringify({ sec_user_id: secUserId }) },
  "用户资料获取失败",
);

export const getUserPosts = (secUserId: string, maxCursor: number) => apiRequest<UserPostsPage>(
  "/api/user-posts",
  {
    method: "POST",
    body: JSON.stringify({ sec_user_id: secUserId, max_cursor: maxCursor, count: 12 }),
  },
  "更多作品获取失败",
);

export type UserContentKind = "posts" | "likes" | "mix";
export type ConnectionKind = "following" | "followers";
export type LibraryKind = "collections" | "folders" | "folder_posts" | "music";
export type FeedKind = "recommended" | "following" | "friends";

const postCapability = <T>(path: string, body: Record<string, unknown>, fallback: string) =>
  apiRequest<T>(path, { method: "POST", body: JSON.stringify(body) }, fallback);

export const getComments = (awemeId: string, cursor = 0) =>
  postCapability<CapabilityPage<CommentItem>>("/api/capabilities/comments", { aweme_id: awemeId, cursor, count: 20 }, "评论获取失败");

export const getCommentReplies = (awemeId: string, commentId: string, cursor = 0) =>
  postCapability<CapabilityPage<CommentItem>>("/api/capabilities/comment-replies", { aweme_id: awemeId, comment_id: commentId, cursor, count: 20 }, "评论回复获取失败");

export const getRelatedPosts = (awemeId: string) =>
  postCapability<CapabilityPage<AwemeSummary>>("/api/capabilities/related-posts", { aweme_id: awemeId, count: 20 }, "相关推荐获取失败");

export const getUserContent = (kind: UserContentKind, target: string, cursor = 0) =>
  postCapability<CapabilityPage<AwemeSummary>>("/api/capabilities/user-content", {
    kind,
    ...(kind === "mix" ? { mix_id: target } : { sec_user_id: target }),
    cursor,
    count: 12,
  }, "用户内容获取失败");

export const getConnections = (kind: ConnectionKind, secUserId: string, userId: string, cursor = 0) =>
  postCapability<CapabilityPage<UserSummary>>("/api/capabilities/connections", { kind, sec_user_id: secUserId, user_id: userId, cursor, count: 20 }, "用户关系获取失败");

export const getAccountLibrary = (kind: LibraryKind, folderId: string, cursor = 0) =>
  postCapability<CapabilityPage<AwemeSummary | CollectionFolder | CollectedMusic>>("/api/capabilities/account-library", {
    kind,
    cursor,
    count: 12,
    ...(folderId ? { folder_id: folderId } : {}),
  }, "账号收藏获取失败");

export const getFeed = (kind: FeedKind, cursor = 0) =>
  postCapability<CapabilityPage<AwemeSummary>>("/api/capabilities/feed", { kind, cursor, count: 12 }, "Feed 获取失败");

export const searchUserPosts = (secUserId: string, keyword: string, cursor = 0) =>
  postCapability<CapabilityPage<AwemeSummary>>("/api/capabilities/user-search", { sec_user_id: secUserId, keyword, cursor, count: 10 }, "用户作品搜索失败");

export const getSuggestions = (query: string) =>
  postCapability<CapabilityPage<string>>("/api/capabilities/suggestions", { query, count: 10 }, "搜索推荐词获取失败");

export const getLiveRoom = (roomId: string) =>
  postCapability<LiveRoomPayload>("/api/capabilities/live-room", { room_id: roomId }, "直播间信息获取失败");

export const getLiveStatus = (userId: string) =>
  postCapability<CapabilityPage<Record<string, unknown>>>("/api/capabilities/live-status", { user_id: userId }, "直播状态获取失败");

export const getLiveMessages = (roomId: string, userUniqueId: string) =>
  postCapability<CapabilityPage<Record<string, unknown>>>("/api/capabilities/live-messages", { room_id: roomId, user_unique_id: userUniqueId }, "直播弹幕握手数据获取失败");

export const getAccountProfile = () =>
  postCapability<AccountProfilePayload>("/api/capabilities/account-profile", {}, "当前账号信息获取失败");

export const getFollowingLive = () =>
  postCapability<CapabilityPage<LiveRoomInfo>>("/api/capabilities/following-live", {}, "关注直播获取失败");
