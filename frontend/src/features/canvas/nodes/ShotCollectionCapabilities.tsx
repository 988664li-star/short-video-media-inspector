import { LoaderCircle, ScanSearch } from "lucide-react";
import { NodeToolbar, Position } from "@xyflow/react";

import type { CanvasNode } from "../../../types/canvas";
import { useCanvasNodeActions } from "./CanvasNodeActions";

interface ShotCollectionCapabilitiesProps {
  id: string;
  node: CanvasNode;
  selected: boolean;
}

export function ShotCollectionCapabilities({ id, node, selected }: ShotCollectionCapabilitiesProps) {
  const { analyzeReplaceables, replacementAnalysisNodeId } = useCanvasNodeActions();
  const running = replacementAnalysisNodeId === id;
  const ready = Boolean(node.shot_assets?.length);

  return (
    <NodeToolbar
      className="canvas-shot-capabilities"
      isVisible={selected}
      position={Position.Top}
      align="center"
      offset={16}
    >
      <button
        type="button"
        disabled={!ready || running}
        title={ready ? "为每个镜头抽取关键帧，并识别可替换的商品、人物、背景和文字" : "分镜组中暂无镜头片段"}
        onClick={() => void analyzeReplaceables(id)}
      >
        {running ? <LoaderCircle className="spin" /> : <ScanSearch />}
        {running ? "正在识别可替换对象…" : "识别可替换对象"}
      </button>
    </NodeToolbar>
  );
}
