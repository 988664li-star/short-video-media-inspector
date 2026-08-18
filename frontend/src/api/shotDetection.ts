import { API_BASE_URL, apiRequest } from "./client";
import type {
  ReplicaPlaybookResult,
  SceneVisualAnalysisResult,
  ShotDetectionResult,
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

export function analyzeScenes(analysisId: string, context: string, force = false) {
  return apiRequest<SceneVisualAnalysisResult>(
    `/api/shot-detection/${analysisId}/scene-analysis`,
    {
      method: "POST",
      body: JSON.stringify({ context, force }),
    },
    "镜头视觉分析失败",
  );
}

export type SceneAnalysisStreamEvent =
  | { type: "progress"; message: string }
  | { type: "scene"; analysis: SceneVisualAnalysisResult["scene_analyses"][number]; completed: number; total: number }
  | { type: "completed"; result: SceneVisualAnalysisResult };

export async function streamSceneAnalysis(
  analysisId: string,
  context: string,
  force: boolean,
  onEvent: (event: SceneAnalysisStreamEvent) => void,
) {
  const response = await fetch(`${API_BASE_URL}/api/shot-detection/${analysisId}/scene-analysis/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ context, force }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(payload.detail || "镜头视觉分析失败");
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
    if (event === "error") throw new Error(String(payload.message || "镜头视觉分析失败"));
    if (event === "progress") onEvent({ type: "progress", message: String(payload.message || "正在分析") });
    if (event === "scene" && payload.analysis && typeof payload.completed === "number" && typeof payload.total === "number") {
      onEvent({ type: "scene", analysis: payload.analysis as SceneVisualAnalysisResult["scene_analyses"][number], completed: payload.completed, total: payload.total });
    }
    if (event === "completed" && payload.result) onEvent({ type: "completed", result: payload.result as SceneVisualAnalysisResult });
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

export function buildReplicaPlaybook(analysisId: string) {
  return apiRequest<ReplicaPlaybookResult>(
    `/api/shot-detection/${analysisId}/replica-playbook`,
    { method: "POST" },
    "生成复刻方案失败",
  );
}
