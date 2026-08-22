import { NodeToolbar, Position, useStore, useViewport } from "@xyflow/react";

import type { CanvasNode } from "../../../types/canvas";
import { CanvasNodeComposer } from "./CanvasNodeComposer";

interface CanvasNodeComposerToolbarProps {
  id: string;
  node: CanvasNode;
  selected: boolean;
  positionAbsoluteX: number;
  positionAbsoluteY: number;
  width?: number | null;
  height?: number | null;
  actionLabel: string;
  promptPlaceholder: string;
  allowSourceUrl?: boolean;
  mode?: "generate" | "instruction";
  assistantTitle?: string;
  assistantDescription?: string;
}

export function CanvasNodeComposerToolbar({
  id,
  node,
  selected,
  positionAbsoluteX,
  positionAbsoluteY,
  width,
  height,
  actionLabel,
  promptPlaceholder,
  allowSourceUrl = false,
  mode = "generate",
  assistantTitle,
  assistantDescription,
}: CanvasNodeComposerToolbarProps) {
  const flowWidth = useStore((state) => state.width);
  const flowHeight = useStore((state) => state.height);
  const viewport = useViewport();
  const measuredWidth = width ?? 320;
  const measuredHeight = height ?? 250;
  const panelHalfWidth = 390;
  const nodeCenterX = (positionAbsoluteX + measuredWidth / 2) * viewport.zoom + viewport.x;
  const nodeBottom = (positionAbsoluteY + measuredHeight) * viewport.zoom + viewport.y;
  const spaceBelow = flowHeight - nodeBottom - 18;
  const availablePanelHeight = Math.max(96, Math.floor(spaceBelow));
  const toolbarAlign = nodeCenterX - panelHalfWidth < 18
    ? "start"
    : nodeCenterX + panelHalfWidth > flowWidth - 18
      ? "end"
      : "center";

  return (
    <NodeToolbar
      className="canvas-node__ai-toolbar"
      isVisible={selected}
      position={Position.Bottom}
      align={toolbarAlign}
      offset={16}
      style={{ maxHeight: availablePanelHeight, overflowX: "hidden", overflowY: "auto" }}
    >
      <CanvasNodeComposer
        nodeId={id}
        node={node}
        actionLabel={actionLabel}
        promptPlaceholder={promptPlaceholder}
        allowSourceUrl={allowSourceUrl}
        mode={mode}
        assistantTitle={assistantTitle}
        assistantDescription={assistantDescription}
      />
    </NodeToolbar>
  );
}
