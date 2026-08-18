import { useCallback, useRef } from "react";

import { ShotDetectionPanel } from "../features/replication/ShotDetectionPanel";
import { ViralRemixCenter } from "../features/replication/ViralRemixCenter";
import type { InspectorController } from "../hooks/useInspector";

interface ReplicationPageProps {
  inspector: InspectorController;
  onReset: () => void;
}

export function ReplicationPage({ inspector, onReset }: ReplicationPageProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const seekToShot = useCallback((seconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    video.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  return (
    <div className="replication-page">
      <ViralRemixCenter
        data={inspector.data}
        shareText={inspector.shareText}
        platform={inspector.platform}
        loading={inspector.loading}
        message={inspector.message}
        messageTone={inspector.messageTone}
        onShareTextChange={inspector.setShareText}
        onPlatformChange={inspector.setPlatform}
        onResolve={() => void inspector.resolve()}
        onReset={onReset}
        videoRef={videoRef}
      >
        {inspector.data?.video ? (
          <aside className="replication-analysis-sidebar" aria-label="分镜分析">
            <ShotDetectionPanel data={inspector.data} onSeek={seekToShot} />
          </aside>
        ) : null}
      </ViralRemixCenter>
    </div>
  );
}
