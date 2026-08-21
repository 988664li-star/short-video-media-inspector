import { CheckCircle2, Clapperboard, Expand, LoaderCircle, RotateCw, TriangleAlert } from "lucide-react";
import type { NodeProps } from "@xyflow/react";

import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeShell } from "./CanvasNodeShell";
import type { CanvasFlowNode } from "./flowTypes";
import { ShotCollectionCapabilities } from "./ShotCollectionCapabilities";

const PREVIEW_LIMIT = 4;

function replacementStatus(status: string) {
  return { pending: "待提交", queued: "排队中", running: "生成中", succeeded: "替换版", failed: "生成失败" }[status] || status;
}

function statusIcon(status: string) {
  if (status === "succeeded") return <CheckCircle2 />;
  if (status === "failed") return <TriangleAlert />;
  return <LoaderCircle className="spin" />;
}

export function ShotCollectionNode({ id, data, selected, dragging }: NodeProps<CanvasFlowNode>) {
  const { previewMedia } = useCanvasNodeActions();
  const { node } = data;
  const shots = node.shot_assets ?? [];
  const replacementShots = shots.filter((shot) => (shot.replacement_versions ?? []).length > 0).slice(-PREVIEW_LIMIT);
  const previews = [...replacementShots, ...shots.filter((shot) => !replacementShots.some((replacementShot) => replacementShot.asset_id === shot.asset_id))]
    .slice(0, PREVIEW_LIMIT);
  const latestVersions = shots.flatMap((shot) => (shot.replacement_versions ?? []).slice(-1));
  const activeCount = latestVersions.filter((version) => version.status === "queued" || version.status === "running").length;
  const completedCount = latestVersions.filter((version) => version.status === "succeeded").length;

  return (
    <>
      <ShotCollectionCapabilities id={id} node={node} selected={selected && !dragging} />
      <CanvasNodeShell node={node} selected={selected} label="分镜组" icon={<Clapperboard />}>
      <section className="canvas-shot-collection">
        <header className="canvas-shot-collection__summary">
          <strong>共 {shots.length} 个镜头</strong>
          <span>{activeCount ? `${activeCount} 个自动刷新中 · ${completedCount} 个已完成` : completedCount ? `${completedCount} 个替换版已完成` : `仅展示 ${Math.min(previews.length, PREVIEW_LIMIT)} 个`}</span>
        </header>
        {previews.length ? (
          <div className="canvas-shot-collection__grid">
            {previews.map((shot) => (
              <article className="canvas-shot-collection__card nodrag nowheel" key={shot.asset_id}>
                <button
                  className="canvas-shot-collection__shot"
                  type="button"
                  title={`预览原镜头 ${String(shot.index).padStart(2, "0")}`}
                  onClick={() => previewMedia({
                    ...node,
                    kind: "video",
                    title: `原镜头 ${String(shot.index).padStart(2, "0")}`,
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
                {(shot.replacement_versions ?? []).slice(-1).map((version) => version.status === "succeeded" && version.result_asset_url ? (
                  <button key={version.task_node_id} className="canvas-shot-collection__replacement" type="button" title={`预览镜头 ${String(shot.index).padStart(2, "0")} 的替换版本`} onClick={() => previewMedia({
                    ...node,
                    kind: "video",
                    title: `替换镜头 ${String(shot.index).padStart(2, "0")}`,
                    detail: `替换主体：${version.source_object_name}`,
                    asset_id: version.result_asset_id,
                    asset_url: version.result_asset_url,
                    asset_name: version.result_asset_name,
                  })}>
                    <RotateCw /> 替换版
                  </button>
                ) : (
                  <p key={version.task_node_id} className={`canvas-shot-collection__status is-${version.status}`}>{statusIcon(version.status)} {replacementStatus(version.status)}</p>
                ))}
              </article>
            ))}
          </div>
        ) : <p className="canvas-shot-collection__empty">暂无可展示的镜头片段</p>}
        <p className="canvas-shot-collection__note">提交后会自动回写并每 5 秒刷新一次；有替换任务的镜头会优先展示，替换版可直接预览。</p>
      </section>
      </CanvasNodeShell>
    </>
  );
}
