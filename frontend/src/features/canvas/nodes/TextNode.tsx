import { Type } from "lucide-react";
import type { NodeProps } from "@xyflow/react";

import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeComposerToolbar } from "./CanvasNodeComposerToolbar";
import { CanvasNodeShell } from "./CanvasNodeShell";
import type { CanvasFlowNode } from "./flowTypes";

export function TextNode({
  id,
  data,
  selected,
  dragging,
  positionAbsoluteX,
  positionAbsoluteY,
  width,
  height,
}: NodeProps<CanvasFlowNode>) {
  const { updateText } = useCanvasNodeActions();
  const { node } = data;
  return (
    <>
      <CanvasNodeComposerToolbar
        id={id}
        node={node}
        selected={selected && !dragging}
        positionAbsoluteX={positionAbsoluteX}
        positionAbsoluteY={positionAbsoluteY}
        width={width}
        height={height}
        actionLabel="生成文本"
        promptPlaceholder="描述你想生成的文本内容；上游节点会自动作为参考…"
      />
      <CanvasNodeShell node={node} selected={selected} label="文本" icon={<Type />}>
        <section className="canvas-node__result canvas-node__result--text">
          <textarea
            className="canvas-node__text-input nodrag nowheel"
            value={node.content}
            rows={5}
            placeholder="输入文本，或选中节点后使用 AI 生成…"
            aria-label="文本节点内容"
            onKeyDown={(event) => event.stopPropagation()}
            onChange={(event) => updateText(id, event.target.value)}
          />
        </section>
      </CanvasNodeShell>
    </>
  );
}
