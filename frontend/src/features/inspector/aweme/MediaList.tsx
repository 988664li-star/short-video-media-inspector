import { useState } from "react";

import { formatCount, formatDuration } from "../../../lib/formatters";
import type { AwemeSummary } from "../../../types/douyin";


interface MediaListProps {
  items: AwemeSummary[];
  onInspect: (item: AwemeSummary) => Promise<boolean>;
  warning?: string;
}

function MediaListItem({ item, onInspect }: { item: AwemeSummary; onInspect: MediaListProps["onInspect"] }) {
  const [busy, setBusy] = useState(false);
  const inspect = async () => {
    setBusy(true);
    await onInspect(item);
    setBusy(false);
  };
  return (
    <article className="media-list-item">
      {item.cover ? <img src={item.cover.proxy_url} alt={item.description} loading="lazy" /> : <div className="media-list-placeholder" />}
      <div className="media-list-body">
        <h3>{item.description}</h3>
        <p>{item.author.nickname} · {item.created_at}</p>
        <div className="media-list-footer">
          <span>{formatDuration(item.duration_ms)} · 赞 {formatCount(item.statistics.likes)} · 评 {formatCount(item.statistics.comments)}</span>
          {item.douyin_url ? (
            <div className="media-list-actions">
              <button type="button" className="inspect-button" disabled={busy} onClick={inspect}>{busy ? "正在切换…" : "查看解析"}</button>
              <a href={item.douyin_url} target="_blank" rel="noreferrer">抖音打开</a>
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export function MediaList({ items, onInspect, warning }: MediaListProps) {
  if (!items.length && !warning) return <p className="panel-empty">暂无可展示的作品。</p>;
  return (
    <div className="media-list">
      {warning ? <p className="inline-warning">近期作品未完整返回：{warning}</p> : null}
      {items.map((item, index) => (
        <MediaListItem
          key={`${item.aweme_id}-${index}`}
          item={item}
          onInspect={onInspect}
        />
      ))}
    </div>
  );
}
