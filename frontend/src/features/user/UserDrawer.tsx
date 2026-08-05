import { useEffect, useRef } from "react";
import { X } from "lucide-react";

import type { AwemeSummary, UserProfilePayload, UserSummary } from "../../types/douyin";
import { formatCount } from "../../lib/formatters";
import { useInfiniteScroll } from "../../hooks/useInfiniteScroll";
import { MediaList } from "../inspector/aweme/MediaList";


interface UserDrawerProps {
  user: UserSummary | null;
  payload: UserProfilePayload | null;
  loading: boolean;
  loadingMore: boolean;
  error: string;
  loadMoreError: string;
  onClose: () => void;
  onInspect: (item: AwemeSummary) => Promise<boolean>;
  onLoadMore: () => void;
}

const statRows = (profile: UserProfilePayload["profile"]) => [
  ["粉丝", formatCount(profile.follower_count)], ["关注", formatCount(profile.following_count)],
  ["获赞", formatCount(profile.total_favorited)], ["作品", formatCount(profile.aweme_count)],
  ["喜欢", formatCount(profile.favoriting_count)], ["合集", formatCount(profile.mix_count)],
] as const;

const infoRows = (profile: UserProfilePayload["profile"]) => [
  ["IP 属地", profile.ip_location], ["城市", profile.city], ["国家/地区", profile.country],
  ["性别", profile.gender === 1 ? "男" : profile.gender === 2 ? "女" : null],
  ["年龄", Number(profile.user_age) > 0 ? profile.user_age : null],
  ["直播状态", profile.live_status === 1 ? "直播中" : profile.live_status === 0 ? "未开播" : profile.live_status],
  ["账号状态", profile.is_ban === true ? "已封禁" : profile.is_ban === false ? "正常" : null],
  ["Sec UID", profile.sec_user_id],
] as const;

export function UserDrawer({
  user, payload, loading, loadingMore, error, loadMoreError,
  onClose, onInspect, onLoadMore,
}: UserDrawerProps) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const drawer = useRef<HTMLElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const hasMore = Boolean(payload?.pagination.has_more);
  const sentinel = useInfiniteScroll(drawer, hasMore && !loadingMore && !loadMoreError, onLoadMore);
  useEffect(() => {
    if (!user) return;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
      returnFocus.current?.focus();
      returnFocus.current = null;
    };
  }, [user, onClose]);
  if (!user) return null;
  const profile = payload?.profile;
  const inspect = async (item: AwemeSummary) => {
    onClose();
    return onInspect(item);
  };
  return (
    <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside ref={drawer} className="user-drawer scroll-surface" role="dialog" aria-modal="true" aria-labelledby="drawerTitle">
        <header className="drawer-header">
          <div><span>公开用户资料</span><h2 id="drawerTitle">{profile?.nickname || user.nickname}</h2></div>
          <button ref={closeButton} type="button" className="drawer-close" onClick={onClose} aria-label="关闭用户资料"><X /></button>
        </header>
        {loading ? <div className="drawer-loading"><span className="loading-ring" /><p>正在获取用户资料和最近作品…</p></div> : null}
        {error ? <div className="drawer-error">{error}</div> : null}
        {profile ? (
          <div className="drawer-content">
            <div className="drawer-profile">
              <div className="drawer-avatar" style={profile.avatar ? { backgroundImage: `url("${profile.avatar.proxy_url}")` } : undefined} />
              <div>
                <h3>{profile.nickname}</h3>
                <p>{profile.unique_id ? `抖音号 ${profile.unique_id}` : `UID ${profile.uid || "未公开"}`}</p>
                <p>{profile.signature || "（未返回用户简介）"}</p>
                {profile.profile_url ? <a href={profile.profile_url} target="_blank" rel="noreferrer">在抖音打开主页</a> : null}
              </div>
            </div>
            <dl className="drawer-stats">
              {statRows(profile).map(([label, value]) => value !== "—" ? <div key={label}><dt>{label}</dt><dd>{value}</dd></div> : null)}
            </dl>
            <dl className="drawer-info">
              {infoRows(profile).map(([label, value]) => value !== null && value !== undefined && value !== "" ? <div key={label}><dt>{label}</dt><dd>{value}</dd></div> : null)}
            </dl>
            <div className="drawer-post-heading"><h3>用户作品</h3><span>已加载 {payload.posts.length} 条 · {payload.access_mode === "login_cookie" ? "登录 Cookie 模式" : "游客模式"}</span></div>
            <MediaList items={payload.posts} warning={payload.posts_error} onInspect={inspect} />
            <div ref={sentinel} className="drawer-pagination" aria-live="polite">
              {loadingMore ? <><span className="loading-ring loading-ring--small" /><p>正在加载更多作品…</p></> : null}
              {loadMoreError ? <><p className="drawer-pagination-error">{loadMoreError}</p><button type="button" className="button button--secondary" onClick={onLoadMore}>重新加载</button></> : null}
              {!loadingMore && !loadMoreError && hasMore ? <p>继续向下滚动加载更多</p> : null}
              {!loadingMore && !loadMoreError && !hasMore && payload.posts.length > 0 ? <p>已加载全部可访问作品</p> : null}
            </div>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
