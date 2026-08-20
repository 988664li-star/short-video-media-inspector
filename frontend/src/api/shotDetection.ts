import { API_BASE_URL, apiRequest } from "./client";
import type {
  ReplicaPlaybookResult,
  ArkFile,
  SeedanceReplacementBinding,
  SeedanceRequestPreviewResult,
  SeedanceModelId,
  SeedanceGenerationMode,
  SeedanceAnchorImagePreviewResult,
  SeedanceWorkspaceResult,
  SavedShotAnalysisState,
  ShotDetectionResult,
  StoryboardScriptResult,
} from "../types/shotDetection";

export function detectShots(awemeId: string, mediaUrl: string) {
  return apiRequest<ShotDetectionResult>(
    "/api/shot-detection",
    {
      method: "POST",
      body: JSON.stringify({ aweme_id: awemeId, media_url: mediaUrl }),
    },
    "自动分镜失败",
  );
}

export function buildReplicaPlaybook(analysisId: string) {
  return apiRequest<ReplicaPlaybookResult>(
    `/api/shot-detection/${analysisId}/replica-playbook`,
    { method: "POST" },
    "生成替换方案失败",
  );
}

export function getSavedShotAnalysisState(analysisId: string) {
  return apiRequest<SavedShotAnalysisState>(
    `/api/shot-detection/${analysisId}/saved-state`,
    {},
    "恢复已保存分析失败",
  );
}

export interface SeedanceWorkspaceInput {
  model: SeedanceModelId;
  generation_mode: SeedanceGenerationMode;
  source_video_file_id: string;
  prompt: string;
  bindings: SeedanceReplacementBinding[];
}

export function listArkFiles(analysisId: string) {
  return apiRequest<{ files: ArkFile[] }>(
    `/api/shot-detection/${analysisId}/ark-files`,
    {},
    "读取方舟素材失败",
  );
}

export async function uploadArkFile(analysisId: string, file: File) {
  const data = new FormData();
  data.append("file", file);
  const response = await fetch(
    `${API_BASE_URL}/api/shot-detection/${analysisId}/ark-files`,
    {
      method: "POST",
      body: data,
    },
  );
  const payload = (await response.json().catch(() => ({}))) as ArkFile & {
    detail?: string;
  };
  if (!response.ok) throw new Error(payload.detail || "上传方舟素材失败");
  return payload as ArkFile;
}

export function refreshArkFile(analysisId: string, fileId: string) {
  return apiRequest<ArkFile>(
    `/api/shot-detection/${analysisId}/ark-files/${fileId}/refresh`,
    { method: "POST" },
    "刷新方舟素材状态失败",
  );
}

export function getSeedanceWorkspace(analysisId: string) {
  return apiRequest<SeedanceWorkspaceResult>(
    `/api/shot-detection/${analysisId}/seedance-workspace`,
    {},
    "读取 Seedance 测试工作台失败",
  );
}

export function saveSeedanceWorkspace(
  analysisId: string,
  workspace: SeedanceWorkspaceInput,
) {
  return apiRequest<SeedanceWorkspaceResult>(
    `/api/shot-detection/${analysisId}/seedance-workspace`,
    { method: "PUT", body: JSON.stringify(workspace) },
    "保存 Seedance 测试工作台失败",
  );
}

export function previewSeedanceRequest(analysisId: string, segmentId?: number) {
  const query = segmentId === undefined ? "" : `?segment_id=${segmentId}`;
  return apiRequest<SeedanceRequestPreviewResult>(
    `/api/shot-detection/${analysisId}/seedance-request-preview${query}`,
    {},
    "生成 Seedance 请求预览失败",
  );
}

export function submitSeedanceTask(analysisId: string, segmentId?: number) {
  return apiRequest<SeedanceWorkspaceResult>(
    `/api/shot-detection/${analysisId}/seedance-tasks`,
    {
      method: "POST",
      body: JSON.stringify(segmentId === undefined ? {} : { segment_id: segmentId }),
    },
    "提交 Seedance 测试失败",
  );
}

export function generateSeedanceAnchorImage(
  analysisId: string,
  segmentId: number,
  force = false,
) {
  return apiRequest<SeedanceWorkspaceResult>(
    `/api/shot-detection/${analysisId}/seedance-anchor-images`,
    { method: "POST", body: JSON.stringify({ segment_id: segmentId, force }) },
    "生成分段视觉锚点图失败",
  );
}

export function getSeedanceAnchorImagePreviews(analysisId: string) {
  return apiRequest<SeedanceAnchorImagePreviewResult>(
    `/api/shot-detection/${analysisId}/seedance-anchor-images/preview`,
    {},
    "读取图片处理预览失败",
  );
}

export function bindSeedanceAnchorImage(
  analysisId: string,
  segmentId: number,
  fileId: string,
) {
  return apiRequest<SeedanceWorkspaceResult>(
    `/api/shot-detection/${analysisId}/seedance-anchor-images/${segmentId}`,
    { method: "PUT", body: JSON.stringify({ file_id: fileId }) },
    "绑定分段视觉锚点图失败",
  );
}

export function refreshSeedanceTask(analysisId: string, localTaskId: string) {
  return apiRequest<SeedanceWorkspaceResult>(
    `/api/shot-detection/${analysisId}/seedance-tasks/${localTaskId}/refresh`,
    { method: "POST" },
    "刷新 Seedance 任务状态失败",
  );
}

export type StoryboardScriptStreamEvent =
  | { type: "progress"; message: string }
  | {
      type: "segment";
      segment: StoryboardScriptResult["segments"][number];
      completed: number;
      total: number;
    }
  | { type: "completed"; result: StoryboardScriptResult };

export async function streamStoryboardScript(
  analysisId: string,
  context: string,
  force: boolean,
  onEvent: (event: StoryboardScriptStreamEvent) => void,
) {
  const response = await fetch(
    `${API_BASE_URL}/api/shot-detection/${analysisId}/storyboard-script/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ context, force }),
    },
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(payload.detail || "生成分段分镜脚本失败");
  }
  if (!response.body) throw new Error("浏览器不支持流式响应");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const dispatch = (block: string) => {
    const event = block.match(/^event:\s*(.+)$/m)?.[1];
    const data = block.match(/^data:\s*(.+)$/m)?.[1];
    if (!event || !data) return;
    const payload = JSON.parse(data) as Record<string, unknown>;
    if (event === "error")
      throw new Error(String(payload.message || "生成分段分镜脚本失败"));
    if (event === "progress")
      onEvent({
        type: "progress",
        message: String(payload.message || "正在生成"),
      });
    if (
      event === "segment" &&
      payload.segment &&
      typeof payload.completed === "number" &&
      typeof payload.total === "number"
    ) {
      onEvent({
        type: "segment",
        segment: payload.segment as StoryboardScriptResult["segments"][number],
        completed: payload.completed,
        total: payload.total,
      });
    }
    if (event === "completed" && payload.result)
      onEvent({
        type: "completed",
        result: payload.result as StoryboardScriptResult,
      });
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      dispatch(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
}
