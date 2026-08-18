import { ClipboardList, LoaderCircle } from "lucide-react";

import { Button } from "../../components/ui/Button";
import type { ReplicaPlaybookResult } from "../../types/shotDetection";

interface ReplicaPlaybookPanelProps {
  result: ReplicaPlaybookResult | null;
  canBuild: boolean;
  loading: boolean;
  error: string;
  onBuild: () => void;
}

export function ReplicaPlaybookPanel({ result, canBuild, loading, error, onBuild }: ReplicaPlaybookPanelProps) {
  const playbook = result?.playbook;
  return (
    <div className="replica-tab-content replica-playbook">
      <div className="replica-tab-content__heading">
        <p>汇总镜头结构、口播与视觉分析，生成可执行的复刻拍摄方案。</p>
        <Button
          variant="primary"
          disabled={!canBuild || loading}
          onClick={onBuild}
          icon={loading ? <LoaderCircle className="spin" /> : <ClipboardList />}
        >
          {loading ? "正在生成" : result ? "重新生成方案" : "生成复刻方案"}
        </Button>
      </div>
      {!canBuild && !result ? <p className="replica-tab-content__hint">请先完成“镜头视觉分析”。</p> : null}
      {error ? <p className="shot-detection__message shot-detection__message--error" role="alert">{error}</p> : null}
      {loading ? <p className="shot-detection__message">正在汇总全片结构与逐镜头拍摄方向，请稍候。</p> : null}
      {playbook ? (
        <div className="replica-playbook__scroll">
          {playbook.video_positioning ? <section className="replica-playbook__positioning"><h4>视频定位</h4><p>{playbook.video_positioning}</p></section> : null}
          {playbook.content_structure?.length ? (
            <section><h4>内容结构</h4><ol className="replica-structure-list">{playbook.content_structure.map((stage) => <li key={`${stage.stage}-${stage.scene_ids.join("-")}`}><strong>{stage.stage}</strong><span>镜头 {stage.scene_ids.join("、")}</span><p>{stage.strategy}</p></li>)}</ol></section>
          ) : null}
          {playbook.replica_shots?.length ? (
            <section><h4>逐镜头复刻</h4><ol className="replica-shots-list">{playbook.replica_shots.map((shot) => <li key={shot.scene_id}><strong>镜头 {String(shot.scene_id).padStart(2, "0")} · {shot.scene_function}</strong><p><b>怎么拍：</b>{shot.shooting_direction}</p><p><b>怎么说：</b>{shot.voiceover_strategy}</p><p><b>怎么剪：</b>{shot.editing_direction}</p></li>)}</ol></section>
          ) : null}
          {playbook.production_checklist?.length ? <section><h4>制作清单</h4><ul className="replica-playbook__list">{playbook.production_checklist.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
          {playbook.data_gaps?.length ? <section><h4>待核对</h4><ul className="replica-playbook__list">{playbook.data_gaps.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
        </div>
      ) : !loading ? <p className="replica-tab-content__empty">生成后将在这里展示视频定位、内容结构与逐镜头复刻方向。</p> : null}
    </div>
  );
}
