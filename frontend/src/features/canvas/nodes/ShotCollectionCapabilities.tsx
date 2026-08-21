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
        title={ready ? "基于全部镜头关键帧识别视频的主要可替换主体，不罗列普通细节物品" : "分镜组中暂无镜头片段"}
        onClick={() => void analyzeReplaceables(id)}
      >
        {running ? <LoaderCircle className="spin" /> : <ScanSearch />}
        {running ? "正在识别主要替换主体…" : "识别主要替换主体"}
      </button>
    </NodeToolbar>
  );
}
