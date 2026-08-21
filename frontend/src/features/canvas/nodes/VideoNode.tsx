import { Expand, Upload, Video } from "lucide-react";
import type { NodeProps } from "@xyflow/react";
import { useRef } from "react";

import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeComposerToolbar } from "./CanvasNodeComposerToolbar";
import { CanvasNodeShell } from "./CanvasNodeShell";
import { VideoNodeCapabilities } from "./VideoNodeCapabilities";
import type { CanvasFlowNode } from "./flowTypes";

export function VideoNode({
  id,
  data,
  selected,
  dragging,
  positionAbsoluteX,
  positionAbsoluteY,
  width,
  height,
}: NodeProps<CanvasFlowNode>) {
  const { previewMedia, uploadNodeAsset, uploadingNodeId } = useCanvasNodeActions();
  const { node } = data;
  const fileInput = useRef<HTMLInputElement>(null);
  const uploading = uploadingNodeId === id;
  return (
    <>
      <VideoNodeCapabilities id={id} node={node} selected={selected && !dragging} />
      <CanvasNodeComposerToolbar
        id={id}
        node={node}
        selected={selected && !dragging}
        positionAbsoluteX={positionAbsoluteX}
        positionAbsoluteY={positionAbsoluteY}
        width={width}
        height={height}
        mode="instruction"
        actionLabel="保存视频指令"
        assistantTitle="视频处理助手"
        assistantDescription="为这个视频配置后续处理要求"
        promptPlaceholder="例如：保留运镜和动作，只替换托盘；或提取分镜、生成字幕、裁剪为 9:16…"
      />
      <CanvasNodeShell node={node} selected={selected} label="视频" icon={<Video />}>
        <div className="canvas-node__media canvas-node__media--video">
          {node.asset_url ? <video src={node.asset_url} muted playsInline preload="metadata" /> : (
            <div className="canvas-node__empty-media">
              <span>上传视频，或在下方配置视频创作指令</span>
              <button type="button" disabled={uploading} onClick={() => fileInput.current?.click()}>
                <Upload /> {uploading ? "上传中…" : "上传视频"}
              </button>
              <input
                ref={fileInput}
                className="canvas-node__upload-input"
                type="file"
                accept="video/*"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.currentTarget.value = "";
                  if (file) void uploadNodeAsset(id, "video", file);
                }}
              />
            </div>
          )}
          {node.asset_url ? (
            <button className="canvas-node__preview nodrag" type="button" onClick={() => previewMedia(node)}>
              <Expand /> 预览
            </button>
          ) : null}
        </div>
        <footer className="canvas-node__footer" title={node.asset_name || node.title}>{node.asset_name || node.title}</footer>
      </CanvasNodeShell>
    </>
  );
}
