import { Frame, LoaderCircle, Scissors } from "lucide-react";
import { NodeToolbar, Position } from "@xyflow/react";

import type { CanvasNode } from "../../../types/canvas";
import { useCanvasNodeActions } from "./CanvasNodeActions";

interface VideoNodeCapabilitiesProps {
  id: string;
  node: CanvasNode;
  selected: boolean;
}

export function VideoNodeCapabilities({ id, node, selected }: VideoNodeCapabilitiesProps) {
  const { extractVideoKeyframes, splitVideoByShots, videoAction } = useCanvasNodeActions();
  const busy = videoAction?.nodeId === id;
  const splitting = videoAction?.nodeId === id && videoAction.type === "split";
  const extracting = videoAction?.nodeId === id && videoAction.type === "keyframes";
  const ready = Boolean(node.asset_id && node.asset_url);

  return (
    <NodeToolbar
      className="canvas-video-capabilities"
      isVisible={selected}
      position={Position.Top}
      align="center"
      offset={16}
    >
      <button
        type="button"
        disabled={!ready || busy}
        title={ready ? "识别镜头边界，并生成按镜头切出的片段节点" : "请先上传或生成视频"}
        onClick={() => void splitVideoByShots(id)}
      >
        {splitting ? <LoaderCircle className="spin" /> : <Scissors />} 按镜头分段
      </button>
      <button
        type="button"
        disabled={!ready || busy}
        title={ready ? "按镜头提取代表关键帧，并生成图片节点" : "请先上传或生成视频"}
        onClick={() => void extractVideoKeyframes(id)}
      >
        {extracting ? <LoaderCircle className="spin" /> : <Frame />} 抽关键帧
      </button>
    </NodeToolbar>
  );
}
