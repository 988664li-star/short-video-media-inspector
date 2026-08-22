import { API_BASE_URL, apiRequest, publicErrorMessage } from "./client";
import type {
  CanvasAsset,
  CanvasDocument,
  CanvasMediaExtractionResult,
  CanvasProject,
  CanvasProjectSummary,
  CanvasReplaceableObject,
  CanvasReplacementResult,
  CanvasReplacementShotPrompt,
  CanvasReplacementSubject,
  CanvasShotAsset,
  CanvasVideoKeyframeResult,
  CanvasVideoModel,
  CanvasVideoShotResult,
} from "../types/canvas";

let videoModelsRequest: Promise<{ models: CanvasVideoModel[] }> | null = null;

export function listCanvasVideoModels() {
  if (!videoModelsRequest) {
    videoModelsRequest = apiRequest<{ models: CanvasVideoModel[] }>(
      "/api/canvas/video-models",
      {},
      "读取视频模型列表失败",
    ).catch((error) => {
      videoModelsRequest = null;
      throw error;
    });
  }
  return videoModelsRequest;
}

export function listCanvasProjects() {
  return apiRequest<{ projects: CanvasProjectSummary[] }>(
    "/api/canvas/projects",
    {},
    "读取历史画布失败",
  );
}

export function getCanvasProject(projectId: string) {
  return apiRequest<{ project: CanvasProject }>(
    `/api/canvas/projects/${projectId}`,
    {},
    "读取画布失败",
  );
}

export function createCanvasProject(name = "未命名画布") {
  return apiRequest<{ project: CanvasProject }>(
    "/api/canvas/projects",
    { method: "POST", body: JSON.stringify({ name }) },
    "新建画布失败",
  );
}

export function getOrCreateDefaultCanvasProject() {
  return apiRequest<{ project: CanvasProject }>(
    "/api/canvas/projects/default",
    { method: "POST" },
    "创建默认画布失败",
  );
}

export function saveCanvasProject(
  projectId: string,
  name: string,
  document: CanvasDocument,
) {
  return apiRequest<{ project: CanvasProject }>(
    `/api/canvas/projects/${projectId}`,
    {
      method: "POST",
      body: JSON.stringify({
        name,
        nodes: document.nodes,
        edges: document.edges,
        viewport: document.viewport,
      }),
    },
    "保存画布失败",
  );
}

export async function uploadCanvasAsset(projectId: string, file: File) {
  const data = new FormData();
  data.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/canvas/projects/${projectId}/assets`, {
    method: "POST",
    body: data,
  });
  const payload = (await response.json().catch(() => ({}))) as { asset?: CanvasAsset; detail?: string };
  if (!response.ok || !payload.asset) {
    throw new Error(publicErrorMessage(payload.detail, "上传画布素材失败"));
  }
  return payload.asset;
}

export function generateCanvasText(projectId: string, prompt: string, context: string) {
  return apiRequest<{ content: string; model: string }>(
    `/api/canvas/projects/${projectId}/generate-text`,
    { method: "POST", body: JSON.stringify({ prompt, context }) },
    "文本生成失败",
  );
}

export function generateCanvasImage(
  projectId: string,
  prompt: string,
  sourceUrl: string,
  sourceAssetIds: string[],
  aspectRatio: string,
) {
  return apiRequest<{ asset: CanvasAsset; model: string }>(
    `/api/canvas/projects/${projectId}/generate-image`,
    {
      method: "POST",
      body: JSON.stringify({
        prompt,
        source_url: sourceUrl || null,
        source_asset_ids: sourceAssetIds,
        aspect_ratio: aspectRatio,
      }),
    },
    "图片生成失败",
  );
}

export function extractCanvasMedia(projectId: string, shareText: string) {
  return apiRequest<CanvasMediaExtractionResult>(
    `/api/canvas/projects/${projectId}/extract-media`,
    {
      method: "POST",
      body: JSON.stringify({ share_text: shareText, platform: "auto" }),
    },
    "链接提取失败",
  );
}

export function splitCanvasVideoByShots(projectId: string, assetId: string) {
  return apiRequest<CanvasVideoShotResult>(
    `/api/canvas/projects/${projectId}/video-shots`,
    { method: "POST", body: JSON.stringify({ asset_id: assetId }) },
    "视频分镜失败",
  );
}

export function extractCanvasVideoKeyframes(projectId: string, assetId: string) {
  return apiRequest<CanvasVideoKeyframeResult>(
    `/api/canvas/projects/${projectId}/video-keyframes`,
    { method: "POST", body: JSON.stringify({ asset_id: assetId }) },
    "视频抽帧失败",
  );
}

export function composeCanvasVideoComparison(
  projectId: string,
  videoAssetIds: string[],
  audioAssetId = "",
) {
  return apiRequest<{
    asset: CanvasAsset;
    input_count: number;
    audio_source_asset_id: string;
  }>(
    `/api/canvas/projects/${projectId}/video-comparisons`,
    {
      method: "POST",
      body: JSON.stringify({
        video_asset_ids: videoAssetIds,
        audio_asset_id: audioAssetId,
      }),
    },
    "对比视频生成失败",
  );
}

export interface CanvasReplacementAnalysisResult {
  keyframes: Array<{
    shot_index: number;
    asset: CanvasAsset;
  }>;
  objects: CanvasReplaceableObject[];
}

export function analyzeCanvasReplaceables(
  projectId: string,
  shots: CanvasShotAsset[],
  sourceContext: string,
) {
  return apiRequest<CanvasReplacementAnalysisResult>(
    `/api/canvas/projects/${projectId}/replacement-analysis`,
    { method: "POST", body: JSON.stringify({ shots, source_context: sourceContext }) },
    "可替换对象识别失败",
  );
}

export function buildCanvasReplacementPrompts(
  projectId: string,
  payload: {
    source_object_name: string;
    source_object_description: string;
    target_description: string;
    target_asset_ids: string[];
    shots: CanvasShotAsset[];
    actions: Array<{ shot_index: number; description: string }>;
    subjects: Array<Omit<CanvasReplacementSubject, "target_node_id"> & { target_asset_ids: string[] }>;
  },
) {
  return apiRequest<{ prompts: CanvasReplacementShotPrompt[] }>(
    `/api/canvas/projects/${projectId}/replacement-prompts`,
    { method: "POST", body: JSON.stringify(payload) },
    "逐镜头提示词生成失败",
  );
}

export function submitCanvasReplacementTasks(
  projectId: string,
  payload: {
    task_node_id: string;
    output_shot_collection_node_id: string;
    model: string;
    target_asset_ids: string[];
    shots: CanvasShotAsset[];
    prompts: CanvasReplacementShotPrompt[];
    confirmed: boolean;
  },
) {
  return apiRequest<{
    output_shot_collection_node_id: string;
    results: Array<CanvasReplacementResult & { result_asset?: CanvasAsset | null }>;
  }>(
    `/api/canvas/projects/${projectId}/replacement-tasks`,
    { method: "POST", body: JSON.stringify(payload) },
    "逐镜头视频替换提交失败",
  );
}

export function refreshCanvasReplacementTask(
  projectId: string,
  payload: {
    model: string;
    provider_task_id: string;
    task_node_id: string;
    output_shot_collection_node_id: string;
    shot: CanvasShotAsset;
    result_asset_id?: string;
  },
) {
  return apiRequest<{ result: CanvasReplacementResult & { result_asset?: CanvasAsset | null } }>(
    `/api/canvas/projects/${projectId}/replacement-tasks/refresh`,
    { method: "POST", body: JSON.stringify(payload) },
    "刷新逐镜头视频替换任务失败",
  );
}

export function composeCanvasReplacementResults(
  projectId: string,
  payload: {
    shots: CanvasShotAsset[];
    results: CanvasReplacementResult[];
    source_audio_asset_id?: string;
  },
) {
  return apiRequest<{ asset: CanvasAsset; used_original_shot_indices: number[] }>(
    `/api/canvas/projects/${projectId}/replacement-compositions`,
    { method: "POST", body: JSON.stringify(payload) },
    "逐镜头替换成片合成失败",
  );
}
