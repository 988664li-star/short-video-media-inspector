import { awemeTypeLabel, formatBytes, formatDuration } from "../../../lib/formatters";
import type { InspectorData } from "../../../types/douyin";
import { InfoGroup, type InfoRow } from "./InfoGroup";


interface DetailPanelProps {
  data: InspectorData;
}

function field(record: Record<string, unknown> | undefined, key: string): unknown {
  return record?.[key];
}

export function DetailPanel({ data }: DetailPanelProps) {
  const music = data.music || {};
  const mix = data.mix;
  const technical = data.video_technical || {};
  const groups: Array<{ title: string; rows: InfoRow[] }> = [
    {
      title: "作品信息",
      rows: [
        ["作品类型", awemeTypeLabel(field(data.content, "aweme_type"))],
        ["媒体类型", field(data.content, "media_type")],
        ["地区", field(data.content, "region")],
        ["位置", field(data.content, "position")],
        ["标题/字幕", data.caption],
        ["评论组 ID", field(data.content, "comment_gid")],
        ["置顶作品", field(data.content, "is_top")],
        ["日常作品", field(data.content, "is_story")],
        ["广告作品", field(data.content, "is_ads")],
      ],
    },
    {
      title: "互动统计",
      rows: [
        ["点赞", data.statistics.likes],
        ["评论", data.statistics.comments],
        ["收藏", data.statistics.collects],
        ["分享", data.statistics.shares],
        ["赞赏", data.statistics.admires],
        ["播放", data.statistics.plays],
      ],
    },
    {
      title: "公开状态与权限",
      rows: [
        ["公开状态", field(data.status, "private_status") === 0 ? "公开" : field(data.status, "private_status")],
        ["已删除", field(data.status, "is_delete")],
        ["已屏蔽", field(data.status, "is_prohibited")],
        ["部分可见", field(data.status, "part_see")],
        ["允许评论", field(data.permissions, "can_comment")],
        ["展示评论", field(data.permissions, "can_show_comment")],
        ["允许转发", field(data.permissions, "can_forward")],
        ["允许分享", field(data.permissions, "can_share")],
        ["允许视频分享", field(data.permissions, "allow_share")],
        ["允许 Dou+", field(data.permissions, "allow_douplus")],
        ["下载设置", field(data.permissions, "download_setting")],
      ],
    },
    {
      title: "原声与配乐",
      rows: [
        ["原声名称", music.title],
        ["原声作者", music.author],
        ["原声 ID", music.id],
        ["时长", music.duration_seconds ? formatDuration(music.duration_seconds * 1000) : null],
        ["状态", music.status === 1 ? "正常" : music.status === 0 ? "不可用" : music.status],
        ["原创音乐", music.is_original],
        ["原创原声", music.is_original_sound],
        ["商业音乐", music.is_commerce_music],
        ["PGC 音乐", music.is_pgc],
        ["所有者", music.owner_nickname],
      ],
    },
    {
      title: "视频技术参数",
      rows: [
        ["格式", technical.format],
        ["画面比例", technical.ratio],
        ["水印", technical.has_watermark],
        ["默认 H.265", technical.is_h265],
        ["HDR", technical.is_hdr],
        ["长视频", technical.is_long_video],
      ],
    },
    {
      title: "合集信息",
      rows: [
        ["合集名称", field(mix, "name")],
        ["合集 ID", field(mix, "id")],
        ["合集描述", field(mix, "description")],
        ["合集类型", field(mix, "type")],
        ["创建时间", field(mix, "id") ? field(mix, "created_at") : null],
        ["更新时间", field(mix, "id") ? field(mix, "updated_at") : null],
        ["合集地址", field(mix, "share_url")],
      ],
    },
    { title: "画面 OCR 文本", rows: [["识别内容", data.ocr_text]] },
  ];

  return (
    <div className="info-groups">
      {groups.map((group) => (
        <InfoGroup key={group.title} title={group.title} rows={group.rows}>
          {group.title === "原声与配乐" && (music.cover || music.audio) ? (
            <div className="music-preview">
              {music.cover ? <img src={music.cover.proxy_url} alt={music.title || "原声封面"} /> : null}
              {music.audio ? <audio controls preload="metadata" src={music.audio.proxy_url} /> : null}
            </div>
          ) : null}
          {group.title === "视频技术参数" && technical.bit_rates?.length ? (
            <div className="bitrate-table-wrap">
              <table className="bitrate-table">
                <thead><tr><th>档位</th><th>编码</th><th>码率</th><th>帧率</th><th>大小</th></tr></thead>
                <tbody>
                  {technical.bit_rates.map((item, index) => (
                    <tr key={`${item.gear}-${item.bit_rate}-${index}`}>
                      <td>{item.gear || "—"}</td><td>{item.codec || "—"}</td>
                      <td>{item.bit_rate ? `${Math.round(item.bit_rate / 1000)} kbps` : "—"}</td>
                      <td>{item.fps || "—"}</td><td>{formatBytes(item.data_size)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </InfoGroup>
      ))}
    </div>
  );
}
