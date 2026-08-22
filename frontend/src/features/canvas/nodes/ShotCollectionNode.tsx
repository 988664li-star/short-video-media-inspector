import { CheckCircle2, Clapperboard, Expand, LoaderCircle, RotateCw, TriangleAlert } from "lucide-react";
import type { NodeProps } from "@xyflow/react";
import { useEffect } from "react";

import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeShell } from "./CanvasNodeShell";
import type { CanvasFlowNode } from "./flowTypes";
import { ShotCollectionCapabilities } from "./ShotCollectionCapabilities";
import { isRefreshableReplacementVersion } from "../replacementHelpers";

const PREVIEW_LIMIT = 4;
const REPLACEMENT_POLL_INTERVAL_MS = 5_000;

function replacementStatus(status: string) {
  return { pending: "待提交", queued: "排队中", running: "生成中", succeeded: "替换版", failed: "生成失败" }[status] || status;
}

function statusIcon(status: string) {
  if (status === "succeeded") return <CheckCircle2 />;
  if (status === "failed") return <TriangleAlert />;
  return <LoaderCircle className="spin" />;
}

export function ShotCollectionNode({ id, data, selected, dragging }: NodeProps<CanvasFlowNode>) {
  const { previewMedia, refreshReplacementOutputGroup } = useCanvasNodeActions();
  const { node } = data;
  const shots = node.shot_assets ?? [];
  const replacementShots = shots.filter((shot) => (shot.replacement_versions ?? []).length > 0).slice(-PREVIEW_LIMIT);
  const previews = [...replacementShots, ...shots.filter((shot) => !replacementShots.some((replacementShot) => replacementShot.asset_id === shot.asset_id))]
    .slice(0, PREVIEW_LIMIT);
  const latestVersions = shots.flatMap((shot) => (shot.replacement_versions ?? []).slice(-1));
  const activeCount = latestVersions.filter((version) => version.status === "queued" || version.status === "running").length;
  const completedCount = latestVersions.filter((version) => version.status === "succeeded").length;
  const isGenerationGroup = node.derived_kind === "shot";
  const shouldAutoRefresh = latestVersions.some(isRefreshableReplacementVersion);

  useEffect(() => {
    if (!shouldAutoRefresh) return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        await refreshReplacementOutputGroup(id);
      } finally {
        if (!cancelled) {
          timer = window.setTimeout(() => void poll(), REPLACEMENT_POLL_INTERVAL_MS);
        }
      }
    };
    timer = window.setTimeout(() => void poll(), REPLACEMENT_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [id, refreshReplacementOutputGroup, shouldAutoRefresh]);

  return (
    <>
      <ShotCollectionCapabilities id={id} node={node} selected={selected && !dragging} />
      <CanvasNodeShell node={node} selected={selected} label={isGenerationGroup ? "编辑片段组" : "替换结果组"} icon={<Clapperboard />}>
      <section className="canvas-shot-collection">
        <header className="canvas-shot-collection__summary">
          <strong>共 {shots.length} 个{isGenerationGroup ? "编辑片段" : "镜头"}</strong>
          <span>{activeCount ? `${activeCount} 个生成中 · ${completedCount} 个已完成` : completedCount ? `${completedCount} 个替换版已完成` : `仅展示 ${Math.min(previews.length, PREVIEW_LIMIT)} 个`}</span>
        </header>
        {previews.length ? (
          <div className="canvas-shot-collection__grid">
            {previews.map((shot) => {
              const versions = shot.replacement_versions ?? [];
              const latestVersion = versions[versions.length - 1];
              const completedVersion = latestVersion?.status === "succeeded" && latestVersion.result_asset_url
                ? latestVersion
                : undefined;
              const previewAsset = completedVersion ? {
                id: completedVersion.result_asset_id,
                url: completedVersion.result_asset_url,
                name: completedVersion.result_asset_name,
              } : {
                id: shot.asset_id,
                url: shot.asset_url,
                name: shot.asset_name,
              };
              return <article className={`canvas-shot-collection__card nodrag nowheel ${completedVersion ? "is-completed" : ""}`} key={shot.asset_id}>
                <button
                  className="canvas-shot-collection__shot"
                  type="button"
                  title={completedVersion
                    ? `播放片段 ${String(shot.index).padStart(2, "0")} 的替换结果`
                    : `预览原始编辑片段 ${String(shot.index).padStart(2, "0")}`}
                  onClick={() => previewMedia({
                    ...node,
                    kind: "video",
                    title: completedVersion
                      ? `替换结果 ${String(shot.index).padStart(2, "0")}`
                      : `原始编辑片段 ${String(shot.index).padStart(2, "0")}`,
                    detail: completedVersion
                      ? `替换主体：${completedVersion.source_object_name}`
                      : `${shot.start_seconds.toFixed(2)}–${shot.end_seconds.toFixed(2)} 秒`,
                    asset_id: previewAsset.id,
                    asset_url: previewAsset.url,
                    asset_name: previewAsset.name,
                  })}
                >
                  <video src={previewAsset.url} muted playsInline preload="metadata" />
                  <span>{completedVersion ? "替换结果" : isGenerationGroup ? "片段" : "镜头"} {String(shot.index).padStart(2, "0")}</span>
                  <Expand aria-hidden="true" />
                </button>
                {latestVersion ? completedVersion ? (
                  <div className="canvas-shot-collection__version-actions" key={latestVersion.task_node_id}>
                    <p><CheckCircle2 /> 已生成，点击上方播放</p>
                    <button type="button" title="预览替换前的原始片段" onClick={() => previewMedia({
                      ...node,
                      kind: "video",
                      title: `原始编辑片段 ${String(shot.index).padStart(2, "0")}`,
                      detail: `${shot.start_seconds.toFixed(2)}–${shot.end_seconds.toFixed(2)} 秒`,
                      asset_id: shot.asset_id,
                      asset_url: shot.asset_url,
                      asset_name: shot.asset_name,
                    })}><RotateCw /> 查看原片</button>
                  </div>
                ) : (
                  <p key={latestVersion.task_node_id} className={`canvas-shot-collection__status is-${latestVersion.status}`}>{statusIcon(latestVersion.status)} {replacementStatus(latestVersion.status)}</p>
                ) : null}
              </article>;
            })}
          </div>
        ) : <p className="canvas-shot-collection__empty">暂无可展示的镜头片段</p>}
        <p className="canvas-shot-collection__note">
          {isGenerationGroup
            ? "按整秒连续切分，每段 4–8 秒；场景切点不影响主体替换任务边界。"
            : "生成结果会自动更新到对应镜头卡片；有替换任务的镜头会优先展示，替换版可直接预览。"}
        </p>
        {node.operation?.error ? <p className="canvas-shot-collection__error" role="alert">{node.operation.error}</p> : null}
        {node.operation?.status === "succeeded" && node.operation.message ? <p className="canvas-shot-collection__success"><CheckCircle2 /> {node.operation.message}</p> : null}
      </section>
      </CanvasNodeShell>
    </>
  );
}
