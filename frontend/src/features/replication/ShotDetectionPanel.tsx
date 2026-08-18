import { Clapperboard, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "../../components/ui/Button";
import { useReplicaPlaybook } from "../../hooks/useReplicaPlaybook";
import { useSceneVisualAnalysis } from "../../hooks/useSceneVisualAnalysis";
import { useShotDetection } from "../../hooks/useShotDetection";
import type { InspectorData } from "../../types/douyin";
import { AutoShotList } from "./AutoShotList";
import { ReplicaPlaybookPanel } from "./ReplicaPlaybookPanel";
import { SceneVisualAnalysisPanel } from "./SceneVisualAnalysisPanel";

interface ShotDetectionPanelProps {
  data: InspectorData;
  onSeek: (seconds: number) => void;
}

type ReplicaTab = "shots" | "visual-analysis" | "playbook";

export function ShotDetectionPanel({ data, onSeek }: ShotDetectionPanelProps) {
  const detector = useShotDetection();
  const visualAnalysis = useSceneVisualAnalysis();
  const playbook = useReplicaPlaybook();
  const [activeTab, setActiveTab] = useState<ReplicaTab>("shots");
  const mediaUrl = data.video?.proxy_url ?? "";
  const result = detector.result;

  useEffect(() => {
    detector.reset();
    visualAnalysis.reset();
    playbook.reset();
    setActiveTab("shots");
  }, [data.aweme_id, mediaUrl, detector.reset, playbook.reset, visualAnalysis.reset]);

  if (!mediaUrl) return null;

  const startDetection = () => {
    visualAnalysis.reset();
    playbook.reset();
    setActiveTab("shots");
    void detector.detect(data.aweme_id, mediaUrl);
  };

  const analysisContext = data.description || data.caption || "";

  return (
    <section className="shot-detection panel" aria-labelledby="shot-detection-heading">
      <div className="shot-detection__heading">
        <div>
          <h3 id="shot-detection-heading">自动分镜</h3>
          <p>下载的视频会集中保存在服务端的分镜目录，识别结果可直接定位参考视频。</p>
        </div>
        <Button
          variant="primary"
          disabled={detector.loading}
          onClick={startDetection}
          icon={detector.loading ? <LoaderCircle className="spin" /> : <Clapperboard />}
        >
          {detector.loading ? "正在识别" : "识别分镜"}
        </Button>
      </div>

      {detector.error ? <p className="shot-detection__message shot-detection__message--error" role="alert">{detector.error}</p> : null}
      {detector.loading ? <p className="shot-detection__message">正在下载并分析视频，请稍候。</p> : null}

      {result ? (
        <>
          <div className="shot-detection__tabs" role="tablist" aria-label="爆款复刻分析结果">
            <button type="button" role="tab" aria-selected={activeTab === "shots"} className={activeTab === "shots" ? "shot-detection__tab shot-detection__tab--active" : "shot-detection__tab"} onClick={() => setActiveTab("shots")}>自动分镜</button>
            <button type="button" role="tab" aria-selected={activeTab === "visual-analysis"} className={activeTab === "visual-analysis" ? "shot-detection__tab shot-detection__tab--active" : "shot-detection__tab"} onClick={() => setActiveTab("visual-analysis")}>镜头视觉分析</button>
            <button type="button" role="tab" aria-selected={activeTab === "playbook"} className={activeTab === "playbook" ? "shot-detection__tab shot-detection__tab--active" : "shot-detection__tab"} onClick={() => setActiveTab("playbook")}>复刻方案</button>
          </div>
          <div className="shot-detection__content" role="tabpanel">
            {activeTab === "shots" ? <AutoShotList result={result} onSeek={onSeek} /> : null}
            {activeTab === "visual-analysis" ? <SceneVisualAnalysisPanel shotResult={result} analysis={visualAnalysis.result} loading={visualAnalysis.loading} error={visualAnalysis.error} progressMessage={visualAnalysis.progressMessage} onAnalyze={() => void visualAnalysis.analyze(result.analysis_id, analysisContext, visualAnalysis.result !== null)} /> : null}
            {activeTab === "playbook" ? <ReplicaPlaybookPanel result={playbook.result} canBuild={visualAnalysis.result !== null} loading={playbook.loading} error={playbook.error} onBuild={() => void playbook.build(result.analysis_id)} /> : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
