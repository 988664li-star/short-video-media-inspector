import { Clapperboard, Expand } from "lucide-react";
import type { NodeProps } from "@xyflow/react";

import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeShell } from "./CanvasNodeShell";
import type { CanvasFlowNode } from "./flowTypes";
import { ShotCollectionCapabilities } from "./ShotCollectionCapabilities";

const PREVIEW_LIMIT = 4;

export function ShotCollectionNode({ id, data, selected, dragging }: NodeProps<CanvasFlowNode>) {
  const { previewMedia } = useCanvasNodeActions();
  const { node } = data;
  const shots = node.shot_assets ?? [];
  const previews = shots.slice(0, PREVIEW_LIMIT);

  return (
    <>
      <ShotCollectionCapabilities id={id} node={node} selected={selected && !dragging} />
      <CanvasNodeShell node={node} selected={selected} label="分镜组" icon={<Clapperboard />}>
      <section className="canvas-shot-collection">
        <header className="canvas-shot-collection__summary">
          <strong>共 {shots.length} 个镜头</strong>
          <span>仅展示前 {Math.min(previews.length, PREVIEW_LIMIT)} 个</span>
        </header>
        {previews.length ? (
          <div className="canvas-shot-collection__grid">
            {previews.map((shot) => (
              <button
                className="canvas-shot-collection__shot nodrag nowheel"
                key={shot.asset_id}
                type="button"
                title={`镜头 ${String(shot.index).padStart(2, "0")} · ${shot.start_seconds.toFixed(2)}–${shot.end_seconds.toFixed(2)} 秒`}
                onClick={() => previewMedia({
                  ...node,
                  kind: "video",
                  title: `镜头 ${String(shot.index).padStart(2, "0")}`,
                  detail: `${shot.start_seconds.toFixed(2)}–${shot.end_seconds.toFixed(2)} 秒`,
                  asset_id: shot.asset_id,
                  asset_url: shot.asset_url,
                  asset_name: shot.asset_name,
                })}
              >
                <video src={shot.asset_url} muted playsInline preload="metadata" />
                <span>镜头 {String(shot.index).padStart(2, "0")}</span>
                <Expand aria-hidden="true" />
              </button>
            ))}
          </div>
        ) : <p className="canvas-shot-collection__empty">暂无可展示的镜头片段</p>}
        <p className="canvas-shot-collection__note">完整镜头列表已保存在此节点，后续多镜头处理会按原顺序读取。</p>
      </section>
      </CanvasNodeShell>
    </>
  );
}
