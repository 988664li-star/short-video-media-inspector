import { AvatarButton } from "../../../components/ui/AvatarButton";
import type { AuthorProfile, AwemeSummary, UserSummary } from "../../../types/douyin";
import { InfoGroup } from "../details/InfoGroup";
import { MediaList } from "../aweme/MediaList";


interface AuthorPanelProps {
  author: AuthorProfile;
  posts: AwemeSummary[];
  onOpenUser: (user: UserSummary) => void;
  onInspect: (item: AwemeSummary) => Promise<boolean>;
}

export function AuthorPanel({ author, posts, onOpenUser, onInspect }: AuthorPanelProps) {
  return (
    <div>
      <div className="profile-card">
        <div className="profile-identity">
          <AvatarButton user={author} imageUrl={author.avatar_url} size="large" onOpenUser={onOpenUser} />
          <div>
            <h3>{author.nickname}</h3>
            <p>{author.unique_id ? `抖音号 ${author.unique_id}` : `UID ${author.uid || "—"}`}</p>
            <p>{author.signature || "（未返回作者简介）"}</p>
          </div>
        </div>
        <InfoGroup
          title="作者公开数据"
          className="profile-stats"
          rows={[
            ["粉丝", author.follower_count], ["关注", author.following_count],
            ["获赞", author.total_favorited], ["作品", author.aweme_count],
            ["喜欢", author.favoriting_count], ["合集", author.mix_count],
            ["IP 属地", author.ip_location], ["城市", author.city],
            ["年龄", Number(author.user_age) > 0 ? author.user_age : "未公开"],
            ["直播状态", author.live_status === 1 ? "直播中" : author.live_status === 0 ? "未开播" : author.live_status],
            ["账号封禁", author.is_ban], ["UID", author.uid], ["Sec UID", author.sec_user_id],
          ]}
        />
      </div>
      <MediaList items={posts} onInspect={onInspect} />
    </div>
  );
}
