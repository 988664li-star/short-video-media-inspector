import type { InspectorData } from "../../types/douyin";
import type { RefObject } from "react";

interface VideoStageProps {
  data: InspectorData;
  videoRef?: RefObject<HTMLVideoElement | null>;
}

export function VideoStage({ data, videoRef }: VideoStageProps) {
  return (
    <div className="video-stage">
      {data.video ? (
        <video
          controls
          playsInline
          preload="metadata"
          ref={videoRef}
          src={data.video.local_proxy_url ?? data.video.proxy_url}
          poster={data.images[0]?.proxy_url}
        />
      ) : (
        <p className="media-unavailable">这条作品没有可播放的视频地址</p>
      )}
    </div>
  );
}
