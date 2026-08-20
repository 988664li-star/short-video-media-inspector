import { Boxes, Clapperboard, LoaderCircle } from "lucide-react";
import { useEffect } from "react";

import { Button } from "../../components/ui/Button";
import { getSavedShotAnalysisState } from "../../api/shotDetection";
import { useReplicaPlaybook } from "../../hooks/useReplicaPlaybook";
import { useShotDetection } from "../../hooks/useShotDetection";
import { useStoryboardScript } from "../../hooks/useStoryboardScript";
import type { InspectorData } from "../../types/douyin";
import { AutoShotList } from "./AutoShotList";
import { ReplicaPlaybookPanel } from "./ReplicaPlaybookPanel";

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
  const result = detector.result;
  const storageKey = savedAnalysisStorageKey(data.aweme_id);

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
    const nextResult = await detector.detect(data.aweme_id, mediaUrl);
    if (nextResult) window.localStorage.setItem(storageKey, nextResult.analysis_id);
  };

  const startProductAnalysis = async () => {
    if (!result) return;
    const script = storyboardScript.result
      ?? await storyboardScript.build(result.analysis_id, data.description || data.caption || "");
    if (!script) return;
    await playbook.build(result.analysis_id);
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
        <div className="local-replacement-flow">
          <section className="local-replacement-flow__step">
            <div className="local-replacement-flow__step-heading">
              <div>
                <span>1</span>
                <div><h4>确认镜头范围</h4><p>已识别的镜头可点击定位回参考视频。</p></div>
              </div>
            </div>
            <AutoShotList result={result} onSeek={onSeek} />
          </section>

          <section className="local-replacement-flow__step">
            <div className="local-replacement-flow__step-heading">
              <div>
                <span>2</span>
                <div><h4>识别可替换商品</h4><p>系统会在后台理解镜头与商品，不要求你查看分镜脚本。</p></div>
              </div>
              <Button
                variant="secondary"
                disabled={analyzingProducts}
                onClick={() => void startProductAnalysis()}
                icon={analyzingProducts ? <LoaderCircle className="spin" /> : <Boxes />}
              >
                {analyzingProducts ? "正在识别商品" : playbook.result ? "重新识别商品" : "识别可替换商品"}
              </Button>
            </div>
            {analyzingProducts ? <p className="shot-detection__message">{storyboardScript.progressMessage || "正在理解镜头中的商品和交互关系。"}</p> : null}
            {analysisError ? <p className="shot-detection__message shot-detection__message--error" role="alert">{analysisError}</p> : null}
          </section>

          {playbook.result ? (
            <ReplicaPlaybookPanel
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
