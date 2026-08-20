import { Clapperboard, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "../../components/ui/Button";
import { getSavedShotAnalysisState } from "../../api/shotDetection";
import { useReplicaPlaybook } from "../../hooks/useReplicaPlaybook";
import { useShotDetection } from "../../hooks/useShotDetection";
import { useStoryboardScript } from "../../hooks/useStoryboardScript";
import type { InspectorData } from "../../types/douyin";
import { AutoShotList } from "./AutoShotList";
import { ReplicaPlaybookPanel } from "./ReplicaPlaybookPanel";
import { StoryboardScriptPanel } from "./StoryboardScriptPanel";

interface ShotDetectionPanelProps {
  data: InspectorData;
  onSeek: (seconds: number) => void;
}

type ReplicaTab = "shots" | "storyboard-script" | "playbook";

function savedAnalysisStorageKey(awemeId: string) {
  return `f2.replication.analysis-id:${awemeId}`;
}

export function ShotDetectionPanel({ data, onSeek }: ShotDetectionPanelProps) {
  const detector = useShotDetection();
  const playbook = useReplicaPlaybook();
  const storyboardScript = useStoryboardScript();
  const [activeTab, setActiveTab] = useState<ReplicaTab>("shots");
  const mediaUrl = data.video?.proxy_url ?? "";
  const result = detector.result;
  const storageKey = savedAnalysisStorageKey(data.aweme_id);

  useEffect(() => {
    detector.reset();
    playbook.reset();
    storyboardScript.reset();
    setActiveTab("shots");
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
      .catch(() => {
        // The server may have expired its cache. Do not show a false failure or start work again.
        window.localStorage.removeItem(storageKey);
      });
    return () => {
      disposed = true;
    };
  }, [
    detector.reset,
    detector.restore,
    mediaUrl,
    playbook.reset,
    playbook.restore,
    storageKey,
    storyboardScript.reset,
    storyboardScript.restore,
  ]);

  useEffect(() => {
    if (result?.analysis_id)
      window.localStorage.setItem(storageKey, result.analysis_id);
  }, [result?.analysis_id, storageKey]);

  if (!mediaUrl) return null;

  const startDetection = () => {
    playbook.reset();
    storyboardScript.reset();
    setActiveTab("shots");
    void detector.detect(data.aweme_id, mediaUrl).then((nextResult) => {
      if (nextResult)
        window.localStorage.setItem(storageKey, nextResult.analysis_id);
    });
  };

  const analysisContext = data.description || data.caption || "";
  const startStoryboardScript = () => {
    if (!result) return;
    playbook.reset();
    void storyboardScript.build(result.analysis_id, analysisContext, storyboardScript.result !== null);
  };

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
            <button type="button" role="tab" aria-selected={activeTab === "storyboard-script"} className={activeTab === "storyboard-script" ? "shot-detection__tab shot-detection__tab--active" : "shot-detection__tab"} onClick={() => setActiveTab("storyboard-script")}>分段分镜脚本</button>
            <button type="button" role="tab" aria-selected={activeTab === "playbook"} className={activeTab === "playbook" ? "shot-detection__tab shot-detection__tab--active" : "shot-detection__tab"} onClick={() => setActiveTab("playbook")}>替换方案</button>
          </div>
          <div className="shot-detection__content" role="tabpanel">
            {activeTab === "shots" ? <AutoShotList result={result} onSeek={onSeek} /> : null}
            {activeTab === "storyboard-script" ? <StoryboardScriptPanel shotResult={result} result={storyboardScript.result} loading={storyboardScript.loading} error={storyboardScript.error} progressMessage={storyboardScript.progressMessage} onBuild={startStoryboardScript} /> : null}
            {activeTab === "playbook" ? <ReplicaPlaybookPanel result={playbook.result} storyboardScript={storyboardScript.result} sourceAssetBaseUrl={result.asset_base_url} canBuild={storyboardScript.result !== null} loading={playbook.loading} error={playbook.error} onBuild={() => void playbook.build(result.analysis_id)} /> : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
