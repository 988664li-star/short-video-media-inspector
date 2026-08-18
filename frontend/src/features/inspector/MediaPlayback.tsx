import { Download } from "lucide-react";

import type { InspectorData } from "../../types/douyin";
import { VideoStage } from "./VideoStage";


interface MediaPlaybackProps {
  data: InspectorData;
}

export function MediaPlayback({ data }: MediaPlaybackProps) {
  return (
    <section className="panel playback-panel" aria-label="媒体播放">
      <VideoStage data={data} />
      <div className="audio-section">
        <div className="subsection-title">
          <h3>视频原音</h3>
          {data.audio ? (
            <a className="icon-link" href={data.audio.proxy_url} download aria-label="下载音频" title="下载音频">
              <Download />
            </a>
          ) : null}
        </div>
        {data.audio ? (
          <audio controls preload="metadata" src={data.audio.proxy_url} />
        ) : (
          <p className="media-unavailable media-unavailable--compact">作品详情中没有独立音轨</p>
        )}
      </div>
    </section>
  );
}
