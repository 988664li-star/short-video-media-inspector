import { Expand, Mic2, Music2 } from "lucide-react";
import type { NodeProps } from "@xyflow/react";

import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeComposerToolbar } from "./CanvasNodeComposerToolbar";
import { CanvasNodeShell } from "./CanvasNodeShell";
import type { CanvasFlowNode } from "./flowTypes";

export function AudioNode({
  id,
  data,
  selected,
  dragging,
  positionAbsoluteX,
  positionAbsoluteY,
  width,
  height,
}: NodeProps<CanvasFlowNode>) {
  const { previewMedia } = useCanvasNodeActions();
  const { node } = data;
  const isMusic = node.kind === "music";
  const label = isMusic ? "作品配乐" : "视频混合音频";

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
        mode="instruction"
        actionLabel="保存音频指令"
        assistantTitle={isMusic ? "配乐处理助手" : "音频处理助手"}
        assistantDescription="为这条音频配置后续处理要求"
        promptPlaceholder={isMusic ? "例如：保留前 15 秒高潮，淡入淡出；或作为生成视频的背景音乐…" : "例如：提取口播、降噪、分离人声与伴奏；或保留为成片原声…"}
      />
      <CanvasNodeShell node={node} selected={selected} label={label} icon={isMusic ? <Music2 /> : <Mic2 />}>
        <section className="canvas-audio-node nodrag nowheel">
          {node.asset_url ? (
            <>
              <audio src={node.asset_url} controls preload="metadata" />
              <button type="button" onClick={() => previewMedia(node)}><Expand /> 单独预览</button>
            </>
          ) : (
            <div className="canvas-audio-node__empty">{node.availability_message || `没有可用的${label}`}</div>
          )}
        </section>
        <footer className="canvas-node__footer" title={node.asset_name || node.title}>{node.asset_name || label}</footer>
        {node.availability_message ? <p className="canvas-audio-node__message">{node.availability_message}</p> : null}
      </CanvasNodeShell>
    </>
  );
}
