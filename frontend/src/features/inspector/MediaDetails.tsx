import { ExternalLink } from "lucide-react";

import { AvatarButton } from "../../components/ui/AvatarButton";
import { formatCount, formatDuration } from "../../lib/formatters";
import type { InspectorData, MediaAsset, UserSummary } from "../../types/douyin";


interface MediaDetailsProps {
  data: InspectorData;
  onOpenUser: (user: UserSummary) => void;
}

function UrlRow({ label, media }: { label: string; media?: MediaAsset }) {
  if (!media?.source_url) return null;
  return (
    <div className="url-row">
      <span>{label}</span>
      <span className="url-row__availability">已获取，可直接查看</span>
      <a href={media.proxy_url} target="_blank" rel="noreferrer" aria-label={`打开${label}`} title={`打开${label}`}><ExternalLink /></a>
    </div>
  );
}

export function MediaDetails({ data, onOpenUser }: MediaDetailsProps) {
  const stats = data.statistics;
  return (
    <aside className="panel details-panel">
      <div className="author-row">
        <AvatarButton
          user={data.author}
          imageUrl={data.author.avatar_url}
          size="medium"
          onOpenUser={onOpenUser}
        />
        <div>
          <h2>{data.author.nickname}</h2>
          {data.author.unique_id ? <span className="author-handle">{data.platform === "tiktok" ? "TikTok" : "抖音号"} {data.author.unique_id}</span> : null}
          <p>{data.description}</p>
          <div className="topic-list">
            {data.hashtags?.map((topic) => <span key={topic.id || topic.name}>#{topic.name}</span>)}
          </div>
        </div>
      </div>
      <dl className="metadata">
        <div><dt>作品 ID</dt><dd>{data.aweme_id}</dd></div>
        <div><dt>发布时间</dt><dd>{data.created_at || "—"}</dd></div>
        <div><dt>时长</dt><dd>{formatDuration(data.duration_ms)}</dd></div>
        <div><dt>分辨率</dt><dd>{data.width && data.height ? `${data.width} × ${data.height}` : "—"}</dd></div>
        <div><dt>互动数据</dt><dd>赞 {formatCount(stats.likes)} · 评 {formatCount(stats.comments)} · 藏 {formatCount(stats.collects)} · 转 {formatCount(stats.shares)}</dd></div>
      </dl>
      <div className="url-list">
        <UrlRow label="音频地址" media={data.audio} />
        <UrlRow label="视频地址" media={data.video} />
        <UrlRow label="配乐地址" media={data.music?.audio} />
        <UrlRow label="封面地址" media={data.images[0]} />
      </div>
      <div className="gallery-section">
        <div className="subsection-title"><h3>图片与封面</h3><span>{data.images.length ? `${data.images.length} 张` : "暂无图片"}</span></div>
        <div className="gallery">
          {data.images.map((image) => (
            <figure key={`${image.label}-${image.proxy_url}`}>
              <a href={image.proxy_url} target="_blank" rel="noreferrer"><img src={image.proxy_url} alt={image.label} loading="lazy" /></a>
              <figcaption>{image.label}</figcaption>
            </figure>
          ))}
        </div>
      </div>
    </aside>
  );
}
