import { Box, Image as ImageIcon, ScanSearch, TextCursorInput, UserRound } from "lucide-react";
import type { NodeProps } from "@xyflow/react";
import { useMemo, useState } from "react";

import type { CanvasReplaceableKind } from "../../../types/canvas";
import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeShell } from "./CanvasNodeShell";
import type { CanvasFlowNode } from "./flowTypes";

function kindIcon(kind: CanvasReplaceableKind) {
  if (kind === "person") return <UserRound />;
  if (kind === "background") return <ImageIcon />;
  if (kind === "text") return <TextCursorInput />;
  return <Box />;
}

function kindLabel(kind: CanvasReplaceableKind) {
  return { product: "商品", person: "人物", background: "背景", text: "文字", other: "对象" }[kind];
}

export function ReplaceableAnalysisNode({ id, data, selected }: NodeProps<CanvasFlowNode>) {
  const { createReplacementTask, previewMedia } = useCanvasNodeActions();
  const { node } = data;
  const objects = node.replaceable_objects ?? [];
  const [view, setView] = useState<"objects" | "shots">("objects");
  const shots = useMemo(() => {
    const entries = new Map<number, typeof objects>();
    objects.forEach((object) => object.shot_indices.forEach((shotIndex) => {
      const current = entries.get(shotIndex) ?? [];
      entries.set(shotIndex, [...current, object]);
    }));
    return [...entries.entries()].sort(([left], [right]) => left - right);
  }, [objects]);

  return (
    <CanvasNodeShell node={node} selected={selected} label="主要替换主体" icon={<ScanSearch />}>
      <section className="canvas-replaceable-analysis nodrag nowheel">
        <header>
          <strong>识别到 {objects.length} 个主要主体</strong>
          <span>可连续选择，加入同一次替换</span>
        </header>
        {node.analysis_keyframes?.length ? <details className="canvas-replaceable-analysis__storyboards">
          <summary>查看时序分镜图</summary>
          <div>
            {node.analysis_keyframes.map((frame) => <button key={frame.asset_id} type="button" onClick={() => previewMedia({
              ...node,
              kind: "image",
              title: `编辑片段 ${String(frame.shot_index).padStart(2, "0")} · 时序分镜图`,
              detail: "该片段按时间抽取的 6 帧，仅用于理解和审核",
              asset_id: frame.asset_id,
              asset_url: frame.asset_url,
              asset_name: frame.asset_name,
            })}>
              <img src={frame.asset_url} alt={`片段 ${frame.shot_index} 时序分镜图`} />
              <span>片段 {String(frame.shot_index).padStart(2, "0")}</span>
            </button>)}
          </div>
        </details> : null}
        {objects.length ? <>
          <div className="canvas-replaceable-analysis__tabs" role="tablist" aria-label="主要主体识别视图">
            <button className={view === "objects" ? "is-active" : ""} type="button" role="tab" aria-selected={view === "objects"} onClick={() => setView("objects")}>按对象看</button>
            <button className={view === "shots" ? "is-active" : ""} type="button" role="tab" aria-selected={view === "shots"} onClick={() => setView("shots")}>按片段看</button>
          </div>
          {view === "objects" ? <div className="canvas-replaceable-analysis__list">
            {objects.map((object) => (
              <article className="canvas-replaceable-analysis__item" key={object.id}>
                <div className="canvas-replaceable-analysis__type">{kindIcon(object.kind)} {kindLabel(object.kind)}</div>
                <strong title={object.description || object.name}>{object.name}</strong>
                <p>出现于 {object.shot_indices.map((index) => String(index).padStart(2, "0")).join("、")} 片段</p>
                <button type="button" title="加入当前视频的同一个多主体替换任务" onClick={() => createReplacementTask(id, object.id)}>加入替换任务</button>
              </article>
            ))}
          </div> : <div className="canvas-replaceable-analysis__shot-list">
            {shots.map(([shotIndex, shotObjects]) => (
              <article key={shotIndex}>
                <strong>片段 {String(shotIndex).padStart(2, "0")}</strong>
                <div>{shotObjects.map((object) => <button key={object.id} type="button" title={`将${object.name}加入同一个替换任务`} onClick={() => createReplacementTask(id, object.id)}>
                  {kindIcon(object.kind)} {object.name}
                </button>)}</div>
              </article>
            ))}
          </div>}
        </> : <p className="canvas-replaceable-analysis__empty">未识别到主要替换主体，可重新分析编辑片段组。</p>}
      </section>
    </CanvasNodeShell>
  );
}
