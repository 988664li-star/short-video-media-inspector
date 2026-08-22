import { LoaderCircle, ScanSearch, Volume2, VolumeX } from "lucide-react";
import { NodeToolbar, Position } from "@xyflow/react";

import type { CanvasNode } from "../../../types/canvas";
import { useCanvasNodeActions } from "./CanvasNodeActions";

interface ShotCollectionCapabilitiesProps {
  id: string;
  node: CanvasNode;
  selected: boolean;
}

export function ShotCollectionCapabilities({ id, node, selected }: ShotCollectionCapabilitiesProps) {
  const {
    analyzeReplaceables,
    composeReplacementOutputGroup,
    getUpstreamNodes,
    replacementAnalysisNodeId,
  } = useCanvasNodeActions();
  const analyzing = replacementAnalysisNodeId === id;
  const composing = node.operation?.status === "running";
  const ready = Boolean(node.shot_assets?.length);
  const latestVersions = (node.shot_assets ?? []).flatMap((shot) => (
    (shot.replacement_versions ?? []).slice(-1)
  ));
  const isResultGroup = node.derived_kind !== "shot" && latestVersions.length > 0;
  const hasCompletedResult = latestVersions.some((version) => version.status === "succeeded");
  const hasActiveResult = latestVersions.some((version) => version.status === "queued" || version.status === "running");
  const connectedAudioNodes = getUpstreamNodes(id).filter((upstreamNode) => (
    (upstreamNode.kind === "audio" || upstreamNode.kind === "music") && upstreamNode.asset_id
  ));
  const connectedAudio = connectedAudioNodes.length === 1 ? connectedAudioNodes[0] : undefined;
  const canCompose = hasCompletedResult && !hasActiveResult && connectedAudioNodes.length <= 1 && !composing;

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
        disabled={!ready || analyzing || composing}
        title={ready ? "读取每个连续片段的时序分镜图，识别视频的主要可替换主体，不罗列普通细节物品" : "编辑片段组中暂无可分析片段"}
        onClick={() => void analyzeReplaceables(id)}
      >
        {analyzing ? <LoaderCircle className="spin" /> : <ScanSearch />}
        {analyzing ? "正在识别主要替换主体…" : "识别主要替换主体"}
      </button>
      {isResultGroup ? <button
        type="button"
        disabled={!canCompose}
        title={connectedAudioNodes.length > 1
          ? "连接了多条音频，请只保留一条音频连接"
          : hasActiveResult
            ? "仍有镜头正在生成，请等待完成后合并"
            : !hasCompletedResult
              ? "还没有成功生成的替换镜头"
              : connectedAudio
                ? `按原顺序合并镜头，并加入音频“${connectedAudio.title}”`
                : "按原顺序合并镜头，未连接音频时生成无声成片"}
        onClick={() => void composeReplacementOutputGroup(id)}
      >
        {composing ? <LoaderCircle className="spin" /> : connectedAudio ? <Volume2 /> : <VolumeX />}
        {composing ? "正在合并成片…" : connectedAudio ? "合并成片 · 含音频" : "合并无声成片"}
      </button> : null}
    </NodeToolbar>
  );
}
