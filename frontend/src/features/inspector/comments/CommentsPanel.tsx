import { AvatarButton } from "../../../components/ui/AvatarButton";
import { formatCount } from "../../../lib/formatters";
import type { CommentItem, UserSummary } from "../../../types/douyin";


interface CommentsPanelProps {
  items: CommentItem[];
  total?: number;
  onOpenUser: (user: UserSummary) => void;
}

export function CommentsPanel({ items, total, onOpenUser }: CommentsPanelProps) {
  if (!items.length) return <p className="panel-empty">暂无可展示的公开评论。</p>;
  return (
    <div>
      <p className="comments-header">已加载 {items.length} 条 · 作品评论总数 {formatCount(total)}</p>
      <div className="comment-list">
        {items.map((comment) => (
          <article className="comment-item" key={comment.id}>
            <AvatarButton user={comment.user} imageUrl={comment.user.avatar?.proxy_url} onOpenUser={onOpenUser} />
            <div className="comment-body">
              <div className="comment-meta">
                <strong>{comment.user.nickname}</strong>
                <span>{[comment.created_at, comment.ip_label, comment.is_hot ? "热门评论" : null].filter(Boolean).join(" · ")}</span>
              </div>
              <p>{comment.text || "（无文字内容）"}</p>
              <span className="comment-metrics">点赞 {formatCount(comment.likes)} · 回复 {formatCount(comment.reply_total)}{comment.is_author_liked ? " · 作者赞过" : ""}</span>
              {comment.images?.length ? (
                <div className="comment-images">
                  {comment.images.map((image) => <img key={image.proxy_url} src={image.proxy_url} alt={image.label} loading="lazy" />)}
                </div>
              ) : null}
              {comment.replies?.length ? (
                <div className="reply-list">
                  {comment.replies.map((reply) => (
                    <div className="reply-item" key={reply.id}>
                      <AvatarButton user={reply.user} imageUrl={reply.user.avatar?.proxy_url} size="reply" onOpenUser={onOpenUser} />
                      <p><strong>{reply.user.nickname}：</strong>{reply.text}</p>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
