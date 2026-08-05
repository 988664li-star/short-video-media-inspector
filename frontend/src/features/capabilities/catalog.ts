export type CapabilityId =
  | "comments"
  | "comment-replies"
  | "related-posts"
  | "user-profile"
  | "user-posts"
  | "user-likes"
  | "mix-posts"
  | "following"
  | "followers"
  | "collections"
  | "folders"
  | "folder-posts"
  | "music"
  | "recommended-feed"
  | "following-feed"
  | "friends-feed"
  | "user-search"
  | "suggestions"
  | "live-room"
  | "live-status"
  | "live-messages"
  | "account-profile"
  | "following-live";

export type CapabilityField = "awemeId" | "commentId" | "secUserId" | "userId" | "mixId" | "folderId" | "keyword" | "query" | "roomId" | "userUniqueId";
export type CapabilityResultKind = "posts" | "comments" | "users" | "folders" | "music" | "words" | "live" | "live-list" | "raw";

export interface CapabilityDefinition {
  id: CapabilityId;
  group: string;
  title: string;
  description: string;
  fields: CapabilityField[];
  resultKind: CapabilityResultKind;
  loginRequired?: boolean;
}

export const FIELD_META: Record<CapabilityField, { label: string; placeholder: string }> = {
  awemeId: { label: "作品 ID", placeholder: "例如 7657015637683801370" },
  commentId: { label: "评论 ID", placeholder: "从评论结果中复制 cid" },
  secUserId: { label: "用户 Sec UID", placeholder: "MS4wLjABAAAA..." },
  userId: { label: "用户 UID（可选）", placeholder: "部分关注/粉丝接口需要" },
  mixId: { label: "合集 ID", placeholder: "mix_id" },
  folderId: { label: "收藏夹 ID", placeholder: "从收藏夹结果中复制" },
  keyword: { label: "作品关键词", placeholder: "搜索该用户发布的作品" },
  query: { label: "搜索词", placeholder: "输入关键词获取联想词" },
  roomId: { label: "直播间/用户 ID", placeholder: "直播 room_id 或用户 uid" },
  userUniqueId: { label: "直播访客 ID", placeholder: "user_unique_id" },
};

export const CAPABILITIES: CapabilityDefinition[] = [
  { id: "comments", group: "评论", title: "作品评论", description: "按游标连续获取公开评论。", fields: ["awemeId"], resultKind: "comments" },
  { id: "comment-replies", group: "评论", title: "评论回复", description: "获取指定评论下的完整回复分页。", fields: ["awemeId", "commentId"], resultKind: "comments" },
  { id: "related-posts", group: "作品", title: "相关推荐", description: "获取指定作品的相关推荐列表。", fields: ["awemeId"], resultKind: "posts" },
  { id: "user-profile", group: "用户内容", title: "用户资料", description: "按 Sec UID 直接查询公开用户资料。", fields: ["secUserId"], resultKind: "users" },
  { id: "user-posts", group: "用户内容", title: "用户作品", description: "获取用户公开发布的作品。", fields: ["secUserId"], resultKind: "posts" },
  { id: "user-likes", group: "用户内容", title: "用户喜欢", description: "账号公开时获取其喜欢列表。", fields: ["secUserId"], resultKind: "posts" },
  { id: "mix-posts", group: "用户内容", title: "合集作品", description: "按合集 ID 获取全部作品。", fields: ["mixId"], resultKind: "posts" },
  { id: "following", group: "社交关系", title: "关注列表", description: "获取目标用户的关注列表。", fields: ["secUserId", "userId"], resultKind: "users", loginRequired: true },
  { id: "followers", group: "社交关系", title: "粉丝列表", description: "获取目标用户的粉丝列表。", fields: ["secUserId", "userId"], resultKind: "users", loginRequired: true },
  { id: "collections", group: "我的账号", title: "收藏作品", description: "读取当前登录账号收藏的作品。", fields: [], resultKind: "posts", loginRequired: true },
  { id: "folders", group: "我的账号", title: "收藏夹", description: "读取当前账号创建的收藏夹。", fields: [], resultKind: "folders", loginRequired: true },
  { id: "folder-posts", group: "我的账号", title: "收藏夹作品", description: "读取指定收藏夹中的作品。", fields: ["folderId"], resultKind: "posts", loginRequired: true },
  { id: "music", group: "我的账号", title: "收藏音乐", description: "读取当前账号收藏的音乐并播放。", fields: [], resultKind: "music", loginRequired: true },
  { id: "account-profile", group: "我的账号", title: "登录环境", description: "验证 Cookie 并读取 F2 返回的当前登录标识。", fields: [], resultKind: "users", loginRequired: true },
  { id: "recommended-feed", group: "内容流", title: "推荐作品", description: "获取抖音推荐 Feed。", fields: [], resultKind: "posts" },
  { id: "following-feed", group: "内容流", title: "关注作品", description: "获取登录账号关注的作品流。", fields: [], resultKind: "posts", loginRequired: true },
  { id: "friends-feed", group: "内容流", title: "朋友作品", description: "获取登录账号的朋友作品流。", fields: [], resultKind: "posts", loginRequired: true },
  { id: "user-search", group: "搜索", title: "用户内搜索", description: "在指定用户主页作品中搜索。", fields: ["secUserId", "keyword"], resultKind: "posts" },
  { id: "suggestions", group: "搜索", title: "搜索联想", description: "获取抖音搜索推荐词。", fields: ["query"], resultKind: "words" },
  { id: "live-room", group: "直播", title: "直播间信息", description: "获取标题、主播、封面和可用流地址。", fields: ["roomId"], resultKind: "live" },
  { id: "live-status", group: "直播", title: "用户直播状态", description: "根据用户 UID 查询是否正在直播。", fields: ["roomId"], resultKind: "raw" },
  { id: "live-messages", group: "直播", title: "弹幕握手数据", description: "获取弹幕 WebSocket 所需的消息、游标与扩展参数。", fields: ["roomId", "userUniqueId"], resultKind: "raw" },
  { id: "following-live", group: "直播", title: "关注直播", description: "获取当前账号关注且正在直播的用户。", fields: [], resultKind: "live-list", loginRequired: true },
];

export const CAPABILITY_GROUPS = [...new Set(CAPABILITIES.map((item) => item.group))];
