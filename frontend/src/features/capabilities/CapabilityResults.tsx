import { useRef } from "react";

import { AvatarButton } from "../../components/ui/AvatarButton";
import { Button } from "../../components/ui/Button";
import { PanelState } from "../../components/ui/PanelState";
import { CommentsPanel } from "../inspector/comments/CommentsPanel";
import { MediaList } from "../inspector/aweme/MediaList";
import { formatCount, formatDuration } from "../../lib/formatters";
import { useInfiniteScroll } from "../../hooks/useInfiniteScroll";
import { copyText } from "../../lib/clipboard";
import type {
  AwemeSummary,
  CollectedMusic,
  CollectionFolder,
  CommentItem,
  LiveRoomInfo,
  UserSummary,
} from "../../types/douyin";
import type { CapabilityOutput } from "./useCapabilityRunner";


interface CapabilityResultsProps {
  output: CapabilityOutput | null;
  loading: boolean;
  loadingMore: boolean;
  error: string;
  onInspect: (item: AwemeSummary) => Promise<boolean>;
  onOpenUser: (user: UserSummary) => void;
  onLoadMore: () => void;
  onUseFolder: (folderId: string) => void;
}

function UserResults({ items, onOpenUser }: { items: UserSummary[]; onOpenUser: (user: UserSummary) => void }) {
  return (
    <div className="capability-user-grid">
      {items.map((user, index) => (
        <article key={user.sec_user_id || user.uid || index} className="capability-user-card">
          <AvatarButton user={user} imageUrl={user.avatar?.proxy_url} size="medium" onOpenUser={onOpenUser} />
          <div><strong>{user.nickname}</strong><span>{user.unique_id ? `抖音号 ${user.unique_id}` : user.uid || "无公开账号 ID"}</span><p>{user.signature || "这个用户没有公开简介。"}</p></div>
        </article>
      ))}
    </div>
  );
}

function FolderResults({ items, onUseFolder }: { items: CollectionFolder[]; onUseFolder: (id: string) => void }) {
  return (
    <div className="capability-card-grid">
      {items.map((item) => (
        <article key={item.id} className="collection-card">
          {item.cover ? <img src={item.cover.proxy_url} alt="" loading="lazy" /> : <div className="collection-card__placeholder" />}
          <div><strong>{item.name}</strong><span>{formatCount(item.count)} 个作品</span><p>{item.description || `收藏夹 ID：${item.id}`}</p><Button variant="text" onClick={() => onUseFolder(item.id)}>查看收藏夹作品</Button></div>
        </article>
      ))}
    </div>
  );
}

function MusicResults({ items }: { items: CollectedMusic[] }) {
  return (
    <div className="capability-card-grid">
      {items.map((item, index) => (
        <article key={item.id || index} className="music-card">
          {item.cover ? <img src={item.cover.proxy_url} alt="" loading="lazy" /> : null}
          <div><strong>{item.title}</strong><span>{item.author || "未知音乐人"} · {formatDuration((item.duration_seconds || 0) * 1000)}</span>{item.audio ? <audio src={item.audio.proxy_url} controls preload="none" /> : <p>接口未返回可播放地址</p>}</div>
        </article>
      ))}
    </div>
  );
}

function LiveCard({ room, onOpenUser }: { room: LiveRoomInfo; onOpenUser: (user: UserSummary) => void }) {
  return (
    <article className="live-card">
      {room.cover ? <img src={room.cover.proxy_url} alt={room.title || "直播封面"} /> : <div className="live-card__placeholder" />}
      <div className="live-card__body">
        <span className={`status-chip ${room.status === 2 ? "status-chip--active" : ""}`}>{room.status === 2 ? "直播中" : `状态 ${room.status ?? "未知"}`}</span>
        <h3>{room.title || "未返回直播标题"}</h3>
        <div className="live-owner"><AvatarButton user={room.owner} imageUrl={room.owner.avatar?.proxy_url} onOpenUser={onOpenUser} /><div><strong>{room.owner.nickname}</strong><span>在线人数 {formatCount(typeof room.viewer_count === "number" ? room.viewer_count : undefined)}</span></div></div>
        <dl><div><dt>Room ID</dt><dd>{room.room_id || "—"}</dd></div><div><dt>Web RID</dt><dd>{room.web_rid || "—"}</dd></div></dl>
      </div>
    </article>
  );
}

export function CapabilityResults(props: CapabilityResultsProps) {
  const { output, loading, loadingMore, error, onInspect, onOpenUser, onLoadMore, onUseFolder } = props;
  const scrollContainer = useRef<HTMLDivElement>(null);
  const hasMore = Boolean(output?.pagination?.has_more);
  const sentinel = useInfiniteScroll(
    scrollContainer,
    hasMore && !loading && !loadingMore && !error,
    onLoadMore,
  );
  if (loading) return <div className="capability-results"><PanelState type="loading" title="正在调用 F2 能力" description="正在请求并整理抖音接口返回数据。" /></div>;
  if (!output) return <div className="capability-results"><PanelState type="empty" title={error ? "调用失败" : "等待自动获取"} description={error || "选择能力或补全参数后，数据会自动显示在这里。"} /></div>;
  const items = output.items;

  return (
    <div className="capability-results">
      <div className="capability-results__heading"><div><h2>调用结果</h2><p>当前累计返回 {items.length} 项</p></div><Button variant="secondary" onClick={() => void copyText(JSON.stringify(output.payload, null, 2))}>复制 JSON</Button></div>
      <div ref={scrollContainer} className="capability-results__scroll scroll-surface" tabIndex={0} aria-label="能力调用结果，可向下滚动加载更多">
        {error ? <p className="inline-message inline-message--error">{error}</p> : null}
        {!items.length ? <p className="panel-empty">接口调用成功，但没有返回可展示的数据。</p> : null}
        {output.kind === "posts" ? <MediaList items={items as AwemeSummary[]} onInspect={onInspect} /> : null}
        {output.kind === "comments" ? <CommentsPanel items={items as CommentItem[]} onOpenUser={onOpenUser} /> : null}
        {output.kind === "users" ? <UserResults items={items as UserSummary[]} onOpenUser={onOpenUser} /> : null}
        {output.kind === "folders" ? <FolderResults items={items as CollectionFolder[]} onUseFolder={onUseFolder} /> : null}
        {output.kind === "music" ? <MusicResults items={items as CollectedMusic[]} /> : null}
        {output.kind === "words" ? <div className="word-cloud">{(items as string[]).map((word) => <span key={word}>{word}</span>)}</div> : null}
        {output.kind === "live" || output.kind === "live-list" ? <div className="live-grid">{(items as LiveRoomInfo[]).map((room, index) => <LiveCard key={room.room_id || index} room={room} onOpenUser={onOpenUser} />)}</div> : null}
        {output.kind === "raw" ? <pre className="raw-json">{JSON.stringify(output.payload, null, 2)}</pre> : null}
        <div ref={sentinel} className="capability-pagination" aria-live="polite">
          {loadingMore ? <><span className="loading-ring loading-ring--small" /><p>正在自动加载下一页…</p></> : null}
          {!loadingMore && !error && hasMore ? <p>继续向下滚动加载更多</p> : null}
          {!loadingMore && !error && !hasMore && items.length > 0 ? <p>已加载全部可访问数据</p> : null}
        </div>
      </div>
    </div>
  );
}
