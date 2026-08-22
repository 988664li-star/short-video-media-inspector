import { Columns3, Frame, LoaderCircle, Scissors } from "lucide-react";
import { NodeToolbar, Position } from "@xyflow/react";

import type { CanvasNode } from "../../../types/canvas";
import { useCanvasNodeActions } from "./CanvasNodeActions";

interface VideoNodeCapabilitiesProps {
  id: string;
  node: CanvasNode;
  selected: boolean;
}

export function VideoNodeCapabilities({ id, node, selected }: VideoNodeCapabilitiesProps) {
  const {
    composeVideoComparison,
    extractVideoKeyframes,
    getUpstreamNodes,
    splitVideoByShots,
    videoAction,
  } = useCanvasNodeActions();
  const busy = videoAction?.nodeId === id;
  const splitting = videoAction?.nodeId === id && videoAction.type === "split";
  const extracting = videoAction?.nodeId === id && videoAction.type === "keyframes";
  const comparing = videoAction?.nodeId === id && videoAction.type === "compare";
  const ready = Boolean(node.asset_id && node.asset_url);
  const upstreamVideoCount = new Set(getUpstreamNodes(id)
    .filter((source) => source.kind === "video" && source.asset_id)
    .map((source) => source.asset_id)).size;
  const comparisonReady = upstreamVideoCount >= 2 && upstreamVideoCount <= 3;

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
        disabled={!comparisonReady || busy}
        title={comparisonReady
          ? `将已连接的 ${upstreamVideoCount} 个视频并排同步合成；优先使用连接的音频，否则使用第一个有音轨的视频`
          : "请连接 2～3 个不同的视频素材"}
        onClick={() => void composeVideoComparison(id)}
      >
        {comparing ? <LoaderCircle className="spin" /> : <Columns3 />} 生成对比视频
      </button>
      <button
        type="button"
        disabled={!ready || busy}
        title={ready ? "按整秒创建 4–8 秒连续编辑片段；场景切点不会拆开同一次主体替换任务" : "请先上传或生成视频"}
        onClick={() => void splitVideoByShots(id)}
      >
        {splitting ? <LoaderCircle className="spin" /> : <Scissors />} 创建编辑片段
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
