import { Box, Image as ImageIcon, ScanSearch, TextCursorInput, UserRound } from "lucide-react";
import type { NodeProps } from "@xyflow/react";

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
  const { createReplacementTask } = useCanvasNodeActions();
  const { node } = data;
  const objects = node.replaceable_objects ?? [];

  return (
    <CanvasNodeShell node={node} selected={selected} label="可替换对象" icon={<ScanSearch />}>
      <section className="canvas-replaceable-analysis nodrag nowheel">
        <header>
          <strong>识别到 {objects.length} 项</strong>
          <span>{node.analysis_keyframes?.length ?? 0} 个镜头关键帧</span>
        </header>
        {objects.length ? <div className="canvas-replaceable-analysis__list">
          {objects.map((object) => (
            <article className="canvas-replaceable-analysis__item" key={object.id}>
              <div className="canvas-replaceable-analysis__type">{kindIcon(object.kind)} {kindLabel(object.kind)}</div>
              <strong title={object.description || object.name}>{object.name}</strong>
              <p>出现于 {object.shot_indices.map((index) => String(index).padStart(2, "0")).join("、")} 镜头</p>
              <button type="button" onClick={() => createReplacementTask(id, object.id)}>替换此对象</button>
            </article>
          ))}
        </div> : <p className="canvas-replaceable-analysis__empty">未识别到可替换对象，可重新分析分镜组。</p>}
      </section>
    </CanvasNodeShell>
  );
}
