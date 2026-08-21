import { Expand, Image as ImageIcon, Upload } from "lucide-react";
import type { NodeProps } from "@xyflow/react";
import { useRef } from "react";

import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeComposerToolbar } from "./CanvasNodeComposerToolbar";
import { CanvasNodeShell } from "./CanvasNodeShell";
import type { CanvasFlowNode } from "./flowTypes";

export function ImageNode({
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
      <CanvasNodeComposerToolbar
        id={id}
        node={node}
        selected={selected && !dragging}
        positionAbsoluteX={positionAbsoluteX}
        positionAbsoluteY={positionAbsoluteY}
        width={width}
        height={height}
        actionLabel="生成图片"
        promptPlaceholder="描述你想生成或修改的画面；当前图片和上游连线会自动作为参考…"
        allowSourceUrl
      />
      <CanvasNodeShell node={node} selected={selected} label="图片" icon={<ImageIcon />}>
        <section className="canvas-node__result canvas-node__result--image">
          <div className="canvas-node__media">
            {node.asset_url ? <img src={node.asset_url} alt={node.title} draggable={false} /> : (
              <div className="canvas-node__empty-media">
                <span>上传参考图，或在下方输入提示词直接生成</span>
                <button type="button" disabled={uploading} onClick={() => fileInput.current?.click()}>
                  <Upload /> {uploading ? "上传中…" : "上传图片"}
                </button>
                <input
                  ref={fileInput}
                  className="canvas-node__upload-input"
                  type="file"
                  accept="image/*"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.currentTarget.value = "";
                    if (file) void uploadNodeAsset(id, "image", file);
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
          <footer className="canvas-node__footer" title={node.asset_name || node.title}>{node.asset_name || "尚未生成图片"}</footer>
        </section>
      </CanvasNodeShell>
    </>
  );
}
