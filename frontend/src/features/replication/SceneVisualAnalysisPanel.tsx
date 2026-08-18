import { Eye, LoaderCircle } from "lucide-react";

import { Button } from "../../components/ui/Button";
import type { SceneVisualAnalysisResult, ShotDetectionResult } from "../../types/shotDetection";
import { formatShotTimestamp } from "./shotTime";

interface SceneVisualAnalysisPanelProps {
  shotResult: ShotDetectionResult;
  analysis: SceneVisualAnalysisResult | null;
  loading: boolean;
  error: string;
  progressMessage: string;
  onAnalyze: () => void;
}

export function SceneVisualAnalysisPanel({
  shotResult,
  analysis,
  loading,
  error,
  progressMessage,
  onAnalyze,
}: SceneVisualAnalysisPanelProps) {
  return (
    <div className="replica-tab-content scene-visual-analysis">
      <div className="replica-tab-content__heading">
        <p>会先用已下载的视频生成带时间戳的口播，再逐镜头结合关键帧进行分析。</p>
        <Button
          variant="primary"
          disabled={loading}
          onClick={onAnalyze}
          icon={loading ? <LoaderCircle className="spin" /> : <Eye />}
        >
          {loading ? "正在分析" : analysis ? "重新分析镜头" : "生成镜头分析"}
        </Button>
      </div>
      {error ? <p className="shot-detection__message shot-detection__message--error" role="alert">{error}</p> : null}
      {loading ? <p className="shot-detection__message">{progressMessage || "正在生成口播、镜头包与视觉分析，请稍候。"}</p> : null}
      {analysis ? (
        <ol className="scene-analysis-list">
          {analysis.scene_analyses.map((scene) => {
            const shot = shotResult.shots.find((item) => item.index === scene.scene_id);
            const cameraMotion = scene.camera_motion === "未知"
              ? "未判定（不等于无运镜）"
              : scene.camera_motion;
            return (
              <li key={scene.scene_id} className="scene-analysis-card">
                <div className="scene-analysis-card__heading">
                  <span>镜头 {String(scene.scene_id).padStart(2, "0")}</span>
                  <strong>{scene.scene_type}</strong>
                </div>
                {shot ? <small>{formatShotTimestamp(shot.start_seconds)} — {formatShotTimestamp(shot.end_seconds)}</small> : null}
                <p>{scene.scene_description}</p>
                <dl>
                  <div><dt>主体</dt><dd>{scene.visual_subject.join("、") || "未知"}</dd></div>
                  <div><dt>动作</dt><dd>{scene.action}</dd></div>
                  <div><dt>景别</dt><dd>{scene.shot_size}</dd></div>
                  <div><dt>机位</dt><dd>{scene.camera_angle}</dd></div>
                  <div><dt>运镜</dt><dd>{cameraMotion}</dd></div>
                </dl>
                <p className="scene-analysis-card__purpose"><strong>转化目的：</strong>{scene.conversion_purpose}</p>
                {scene.evidence.length > 0 ? <ul>{scene.evidence.map((item) => <li key={item}>{item}</li>)}</ul> : null}
              </li>
            );
          })}
        </ol>
      ) : !loading ? <p className="replica-tab-content__empty">生成后将在这里展示每个镜头的画面、动作、景别与转化作用。</p> : null}
    </div>
  );
}
