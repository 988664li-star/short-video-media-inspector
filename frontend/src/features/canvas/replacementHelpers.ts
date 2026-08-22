import type {
  CanvasAsset,
  CanvasReplaceableObject,
  CanvasReplacementTask,
  CanvasReplacementResult,
  CanvasReplacementShotPrompt,
  CanvasShotAsset,
  CanvasShotReplacementVersion,
} from "../../types/canvas";

const LEGACY_REFRESH_VALIDATION_ERROR = /String should match pattern|刷新逐镜头视频替换任务失败/;

export function effectiveReplacementShot(shot: CanvasShotAsset): CanvasShotAsset {
  const versions = shot.replacement_versions ?? [];
  const completed = [...versions].reverse().find((version) => (
    version.status === "succeeded"
    && version.result_asset_id
    && version.result_asset_url
    && version.result_asset_name
  ));
  if (!completed) return shot;
  return {
    ...shot,
    asset_id: completed.result_asset_id!,
    asset_url: completed.result_asset_url!,
    asset_name: completed.result_asset_name!,
  };
}

export function toReplacementResult(result: CanvasReplacementResult & { result_asset?: CanvasAsset | null }): CanvasReplacementResult {
  return {
    shot_index: result.shot_index, source_asset_id: result.source_asset_id, source_asset_name: result.source_asset_name,
    duration_seconds: result.duration_seconds,
    model: result.model,
    provider_task_id: result.provider_task_id, status: result.status,
    result_asset_id: result.result_asset?.id ?? result.result_asset_id ?? "",
    result_asset_url: result.result_asset?.url ?? result.result_asset_url ?? "",
    result_asset_name: result.result_asset?.filename ?? result.result_asset_name ?? "", error: result.error ?? "",
  };
}

export function toShotReplacementVersion(taskNodeId: string, task: CanvasReplacementTask, result: CanvasReplacementResult): CanvasShotReplacementVersion {
  const subjectNames = task.subjects.map((subject) => subject.source_object_name).join("、").slice(0, 160);
  return {
    task_node_id: taskNodeId, source_object_id: task.source_object_id, source_object_name: subjectNames || task.source_object_name,
    model: result.model,
    provider_task_id: result.provider_task_id, status: result.status === "original" ? "pending" : result.status,
    result_asset_id: result.result_asset_id, result_asset_url: result.result_asset_url,
    result_asset_name: result.result_asset_name, error: result.error,
  };
}

export function replacementTaskName(task: CanvasReplacementTask) {
  return task.subjects.map((subject) => subject.source_object_name).join(" + ") || task.source_object_name;
}

export function formatVideoTime(seconds: number) {
  const total = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

export function replaceableKindLabel(kind: CanvasReplaceableObject["kind"]) {
  return {
    product: "商品",
    person: "人物",
    background: "背景",
    text: "文字",
    other: "对象",
  }[kind];
}

export function replacementPromptStatus(status: CanvasReplacementResult["status"]): CanvasReplacementShotPrompt["status"] {
  if (status === "succeeded" || status === "failed" || status === "running" || status === "queued") return status;
  return "pending";
}

export function replacementVersionStatus(status: CanvasReplacementResult["status"]): CanvasShotReplacementVersion["status"] {
  if (status === "succeeded" || status === "failed" || status === "running" || status === "queued") return status;
  return "pending";
}

export function isRefreshableReplacementVersion(version: CanvasShotReplacementVersion) {
  if (!version.provider_task_id) return false;
  if (version.status === "queued" || version.status === "running") return true;
  return version.status === "failed" && LEGACY_REFRESH_VALIDATION_ERROR.test(version.error ?? "");
}

export function sameReplacementVersion(
  left: CanvasShotReplacementVersion,
  right: CanvasShotReplacementVersion,
) {
  return left.provider_task_id === right.provider_task_id
    && left.model === right.model
    && left.status === right.status
    && left.result_asset_id === right.result_asset_id
    && left.result_asset_url === right.result_asset_url
    && left.result_asset_name === right.result_asset_name
    && left.error === right.error;
}
