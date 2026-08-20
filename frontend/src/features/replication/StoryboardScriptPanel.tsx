import { PanelsTopLeft, LoaderCircle } from "lucide-react";

import { Button } from "../../components/ui/Button";
import type { ShotDetectionResult, StoryboardScriptResult } from "../../types/shotDetection";
import { formatShotTimestamp } from "./shotTime";

interface StoryboardScriptPanelProps {
  shotResult: ShotDetectionResult;
  result: StoryboardScriptResult | null;
  loading: boolean;
  error: string;
  progressMessage: string;
  onBuild: () => void;
}

export function StoryboardScriptPanel({
  shotResult,
  result,
  loading,
  error,
  progressMessage,
  onBuild,
}: StoryboardScriptPanelProps) {
  return (
    <div className="replica-tab-content storyboard-script">
      <div className="replica-tab-content__heading">
        <p>根据关键帧、带时间戳的转写，按不超过 15 秒的规则组织完整分镜脚本。优先保留镜头边界；单镜头超过 15 秒时，会在第 14 秒强制切开。</p>
        <Button
          variant="primary"
          disabled={loading}
          onClick={onBuild}
          icon={loading ? <LoaderCircle className="spin" /> : <PanelsTopLeft />}
        >
          {loading ? "正在生成" : result ? "重新生成脚本" : "生成分段脚本"}
        </Button>
      </div>
      {error ? <p className="shot-detection__message shot-detection__message--error" role="alert">{error}</p> : null}
      {loading ? <p className="shot-detection__message">{progressMessage || "正在生成分段分镜脚本，请稍候。"}</p> : null}
      {result ? (
        <ol className="storyboard-script__segments">
          {result.segments.map((segment) => (
            <li key={segment.segment_id} className="storyboard-script__segment">
              <div className="storyboard-script__segment-heading">
                <div>
                  <strong>片段 {String(segment.segment_id).padStart(2, "0")}</strong>
                  <span>{formatShotTimestamp(segment.start_ms / 1000)} — {formatShotTimestamp(segment.end_ms / 1000)} · {(segment.duration_ms / 1000).toFixed(2)} 秒</span>
                </div>
              </div>
              <img
                className="storyboard-script__contact-sheet"
                src={`${shotResult.asset_base_url}/${segment.contact_sheet}`}
                alt={`片段 ${segment.segment_id} 的拼接分镜图`}
              />
              <p className="storyboard-script__summary">{segment.segment_summary}</p>
              <ol className="storyboard-script__shots">
                {segment.storyboard.map((shot) => (
                  <li key={`${segment.segment_id}-${shot.order}`}>
                    <strong>{String(shot.order).padStart(2, "0")} · {shot.title}</strong>
                    <span>{formatShotTimestamp(shot.time_range_ms[0] / 1000)} — {formatShotTimestamp(shot.time_range_ms[1] / 1000)} · {shot.scene_type}</span>
                    <p>{shot.visual_description}</p>
                    <dl>
                      <div><dt>动作</dt><dd>{shot.action}</dd></div>
                      <div><dt>景别</dt><dd>{shot.shot_size}</dd></div>
                      <div><dt>机位</dt><dd>{shot.camera_angle}</dd></div>
                      <div><dt>运镜</dt><dd>{shot.camera_motion === "未知" ? "未判定" : shot.camera_motion}</dd></div>
                    </dl>
                    <p><b>原声/对白：</b>{shot.voiceover}</p>
                    <p><b>拍摄与剪辑：</b>{shot.shooting_notes}</p>
                  </li>
                ))}
              </ol>
              <p className="storyboard-script__script"><b>片段脚本：</b>{segment.segment_script}</p>
            </li>
          ))}
        </ol>
      ) : !loading ? <p className="replica-tab-content__empty">生成后将在这里展示每段拼接分镜图，以及模型一次生成的完整分镜脚本。</p> : null}
    </div>
  );
}
