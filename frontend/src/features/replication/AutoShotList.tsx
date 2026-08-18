import { Play } from "lucide-react";

import type { ShotDetectionResult } from "../../types/shotDetection";
import { formatShotTimestamp } from "./shotTime";

interface AutoShotListProps {
  result: ShotDetectionResult;
  onSeek: (seconds: number) => void;
}

export function AutoShotList({ result, onSeek }: AutoShotListProps) {
  return (
    <>
      <div className="shot-detection__summary" role="status">
        <span>识别到 {result.shots.length} 个镜头</span>
        <span>{result.cached ? "已使用已下载的数据" : `耗时 ${result.elapsed_seconds}s`}</span>
      </div>
      <ol className="shot-list">
        {result.shots.map((shot) => (
          <li key={`${shot.index}-${shot.start_seconds}`}>
            <button type="button" onClick={() => onSeek(shot.start_seconds)}>
              <span className="shot-list__index">{String(shot.index).padStart(2, "0")}</span>
              <span className="shot-list__time">{formatShotTimestamp(shot.start_seconds)} — {formatShotTimestamp(shot.end_seconds)}</span>
              <span className="shot-list__duration">{shot.duration_seconds.toFixed(2)} 秒</span>
              <Play aria-hidden="true" />
            </button>
            {shot.selected_frames.length > 0 ? (
              <div className="shot-list__frames" aria-label={`镜头 ${shot.index} 的关键帧`}>
                {shot.selected_frames.map((frame) => (
                  <button
                    type="button"
                    key={frame.path}
                    onClick={() => onSeek(frame.timestamp_seconds)}
                    title={`跳转至 ${formatShotTimestamp(frame.timestamp_seconds)}`}
                  >
                    <img
                      alt={`镜头 ${shot.index} 在 ${formatShotTimestamp(frame.timestamp_seconds)} 的关键帧`}
                      src={`${result.asset_base_url}/${frame.path}`}
                    />
                  </button>
                ))}
              </div>
            ) : null}
          </li>
        ))}
      </ol>
    </>
  );
}
