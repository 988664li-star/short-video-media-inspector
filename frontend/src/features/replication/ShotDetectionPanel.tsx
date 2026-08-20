import { Boxes, Clapperboard, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "../../components/ui/Button";
import { getSavedShotAnalysisState } from "../../api/shotDetection";
import { useReplicaPlaybook } from "../../hooks/useReplicaPlaybook";
import { useShotDetection } from "../../hooks/useShotDetection";
import { useStoryboardScript } from "../../hooks/useStoryboardScript";
import type { InspectorData } from "../../types/douyin";
import { AutoShotList } from "./AutoShotList";
import { ReplicaPlaybookPanel } from "./ReplicaPlaybookPanel";
import {
  ReplacementWorkflowTabs,
  type ReplacementWorkflowStep,
} from "./ReplacementWorkflowTabs";

interface ShotDetectionPanelProps {
  data: InspectorData;
  onSeek: (seconds: number) => void;
}

function savedAnalysisStorageKey(awemeId: string) {
  return `f2.replication.analysis-id:${awemeId}`;
}

export function ShotDetectionPanel({ data, onSeek }: ShotDetectionPanelProps) {
  const detector = useShotDetection();
  const playbook = useReplicaPlaybook();
  const storyboardScript = useStoryboardScript();
  const mediaUrl = data.video?.proxy_url ?? "";
  const localAnalysisId = data.video?.local_analysis_id;
  const result = detector.result;
  const storageKey = savedAnalysisStorageKey(data.aweme_id);
  const [activeStep, setActiveStep] = useState<ReplacementWorkflowStep>(1);
  const [availableStep, setAvailableStep] = useState<ReplacementWorkflowStep>(1);

  useEffect(() => {
    detector.reset();
    playbook.reset();
    storyboardScript.reset();
    const savedAnalysisId = window.localStorage.getItem(storageKey);
    if (!savedAnalysisId) return undefined;

    let disposed = false;
    void getSavedShotAnalysisState(savedAnalysisId)
      .then((savedState) => {
        if (disposed) return;
        detector.restore(savedState.detection);
        storyboardScript.restore(savedState.storyboard_script);
        playbook.restore(savedState.replica_playbook);
        if (savedState.replica_playbook) {
          setAvailableStep(2);
          setActiveStep(2);
        }
      })
      .catch(() => window.localStorage.removeItem(storageKey));
    return () => {
      disposed = true;
    };
  }, [detector.reset, detector.restore, mediaUrl, playbook.reset, playbook.restore, storageKey, storyboardScript.reset, storyboardScript.restore]);

  useEffect(() => {
    if (result?.analysis_id)
      window.localStorage.setItem(storageKey, result.analysis_id);
  }, [result?.analysis_id, storageKey]);

  if (!mediaUrl) return null;

  const startDetection = async () => {
    playbook.reset();
    storyboardScript.reset();
    const nextResult = await detector.detect(
      data.aweme_id,
      mediaUrl,
      localAnalysisId,
    );
    if (nextResult) {
      window.localStorage.setItem(storageKey, nextResult.analysis_id);
      setAvailableStep(1);
      setActiveStep(1);
    }
  };

  const startProductAnalysis = async () => {
    if (!result) return;
    const script = storyboardScript.result
      ?? await storyboardScript.build(result.analysis_id, data.description || data.caption || "");
    if (!script) return;
    const nextPlaybook = await playbook.build(result.analysis_id);
    if (nextPlaybook) {
      setAvailableStep(2);
      setActiveStep(2);
    }
  };

  const analyzingProducts = storyboardScript.loading || playbook.loading;
  const analysisError = storyboardScript.error || playbook.error;

  return (
    <section className="shot-detection panel" aria-labelledby="shot-detection-heading">
      <div className="shot-detection__heading">
        <div>
          <h3 id="shot-detection-heading">商品替换工作流</h3>
          <p>先拆出镜头，再确认商品和它出现的时间段；系统不会替换其他对象。</p>
        </div>
        <Button
          variant="primary"
          disabled={detector.loading}
          onClick={() => void startDetection()}
          icon={detector.loading ? <LoaderCircle className="spin" /> : <Clapperboard />}
        >
          {detector.loading ? "正在理解视频" : result ? "重新识别镜头" : "开始识别镜头"}
        </Button>
      </div>

      {detector.error ? <p className="shot-detection__message shot-detection__message--error" role="alert">{detector.error}</p> : null}
      {detector.loading ? <p className="shot-detection__message">正在提取视频并识别镜头，请稍候。</p> : null}

      {result ? (
        <div className="replacement-wizard">
          <ReplacementWorkflowTabs
            activeStep={activeStep}
            availableStep={availableStep}
            onSelect={setActiveStep}
          />
          {activeStep === 1 ? (
            <section className="replacement-wizard__stage">
              <div className="replacement-wizard__stage-copy">
                <h4>确认参考视频分析</h4>
                <p>已识别 {result.shots.length} 个镜头。下一步会把相邻镜头合成不超过 15 秒的连续片段，并找出可替换的商品。</p>
              </div>
              <div className="replacement-wizard__summary">
                <b>参考视频已保存到本地</b>
                <span>
                  {result.duration_seconds.toFixed(1)} 秒 · {result.shots.length} 个镜头 · CDN 失效不影响后续操作
                </span>
              </div>
              <div className="replacement-wizard__footer">
                <details className="replacement-wizard__details">
                  <summary>查看镜头明细并定位参考视频</summary>
                  <AutoShotList result={result} onSeek={onSeek} />
                </details>
                <Button
                  variant="primary"
                  disabled={analyzingProducts}
                  onClick={() => void startProductAnalysis()}
                  icon={analyzingProducts ? <LoaderCircle className="spin" /> : <Boxes />}
                >
                  {analyzingProducts ? "正在分析商品" : playbook.result ? "重新分析商品" : "继续：分析商品"}
                </Button>
              </div>
              {analyzingProducts ? <p className="shot-detection__message">{storyboardScript.progressMessage || "正在理解镜头中的商品和交互关系。"}</p> : null}
              {analysisError ? <p className="shot-detection__message shot-detection__message--error" role="alert">{analysisError}</p> : null}
            </section>
          ) : null}
          {playbook.result && activeStep > 1 ? (
            <ReplicaPlaybookPanel
              activeStep={activeStep}
              onStepChange={setActiveStep}
              onUnlockStep={setAvailableStep}
              result={playbook.result}
              storyboardScript={storyboardScript.result}
              sourceAssetBaseUrl={result.asset_base_url}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
