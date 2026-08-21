export type CanvasNodeKind =
  | "text"
  | "image"
  | "video"
  | "shot_collection"
  | "replaceable_analysis"
  | "replacement_task"
  | "extractor"
  | "music"
  | "audio";

export interface CanvasAsset {
  id: string;
  project_id: string;
  filename: string;
  mime_type: string;
  bytes: number;
  created_at: number;
  url: string;
}

export interface CanvasNode {
  id: string;
  kind: CanvasNodeKind;
  x: number;
  y: number;
  title: string;
  detail: string;
  content: string;
  asset_id?: string;
  asset_url?: string;
  asset_name?: string;
  source_extractor_id?: string;
  source_node_id?: string;
  derived_kind?: "shot" | "keyframe";
  shot_assets?: CanvasShotAsset[];
  analysis_keyframes?: CanvasAnalysisKeyframe[];
  replaceable_objects?: CanvasReplaceableObject[];
  replacement_task?: CanvasReplacementTask;
  reference_assets?: CanvasReferenceAsset[];
  availability_message?: string;
  operation?: CanvasNodeOperation;
}

/** A locally stored multimodal material attached to a canvas node. */
export interface CanvasReferenceAsset {
  id: string;
  url: string;
  filename: string;
  mime_type: string;
}

/** Complete, ordered shot data held by one compact "分镜组" canvas node. */
export interface CanvasShotAsset {
  index: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  asset_id: string;
  asset_url: string;
  asset_name: string;
  replacement_versions?: CanvasShotReplacementVersion[];
}

/** One generated replacement version belonging to a source shot. */
export interface CanvasShotReplacementVersion {
  task_node_id: string;
  source_object_id: string;
  source_object_name: string;
  provider_task_id: string;
  status: "pending" | "queued" | "running" | "succeeded" | "failed";
  result_asset_id?: string;
  result_asset_url?: string;
  result_asset_name?: string;
  error?: string;
}

export type CanvasReplaceableKind = "product" | "person" | "background" | "text" | "other";

/** A durable keyframe extracted internally for one source shot. */
export interface CanvasAnalysisKeyframe {
  shot_index: number;
  asset_id: string;
  asset_url: string;
  asset_name: string;
}

/** One object/person/background the visual analysis found across source shots. */
export interface CanvasReplaceableObject {
  id: string;
  kind: CanvasReplaceableKind;
  name: string;
  description: string;
  shot_indices: number[];
  actions: Array<{ shot_index: number; description: string }>;
}

export interface CanvasReplacementShotPrompt {
  shot_index: number;
  prompt: string;
  input_revision?: number;
  status: "pending" | "ready" | "queued" | "running" | "succeeded" | "failed";
  provider_task_id?: string;
  result_asset_id?: string;
  error?: string;
}

export interface CanvasReplacementResult {
  shot_index: number;
  source_asset_id: string;
  source_asset_name: string;
  duration_seconds: number;
  provider_task_id: string;
  status: "pending" | "queued" | "running" | "succeeded" | "failed" | "original";
  result_asset_id?: string;
  result_asset_url?: string;
  result_asset_name?: string;
  error?: string;
}

/** Configuration held by one compact per-object, multi-shot replacement task. */
export interface CanvasReplacementTask {
  analysis_node_id: string;
  shot_collection_node_id: string;
  output_shot_collection_node_id?: string;
  source_object_id: string;
  source_object_kind: CanvasReplaceableKind;
  source_object_name: string;
  source_object_description: string;
  shot_indices: number[];
  actions: Array<{ shot_index: number; description: string }>;
  target_description: string;
  selected_shot_indices: number[];
  shot_prompts: CanvasReplacementShotPrompt[];
}

export interface CanvasExtractedMediaOutput {
  kind: "video" | "music" | "audio";
  label: string;
  available: boolean;
  asset: CanvasAsset | null;
  message: string;
}

export interface CanvasMediaExtractionResult {
  platform: "douyin" | "tiktok";
  aweme_id: string;
  description: string;
  author: { nickname?: string; unique_id?: string };
  duration_ms?: number;
  outputs: Record<"video" | "music" | "audio", CanvasExtractedMediaOutput>;
  warnings: string[];
}

export interface CanvasVideoShot {
  index: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  asset: CanvasAsset;
}

export interface CanvasVideoShotResult {
  source_asset_id: string;
  duration_seconds: number;
  shots: CanvasVideoShot[];
}

export interface CanvasVideoKeyframe {
  shot_index: number;
  timestamp_seconds: number;
  asset: CanvasAsset;
}

export interface CanvasVideoKeyframeResult {
  source_asset_id: string;
  duration_seconds: number;
  frames: CanvasVideoKeyframe[];
}

export interface CanvasNodeOperation {
  prompt: string;
  model: string;
  source_url?: string;
  referenced_asset_ids?: string[];
  style?: string;
  aspect_ratio?: string;
  quality?: string;
  role_mode?: string;
  status: "idle" | "running" | "succeeded" | "failed";
  error?: string;
  message?: string;
}

export interface CanvasEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
}

export interface CanvasViewport {
  x: number;
  y: number;
  scale: number;
}

export interface CanvasDocument {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  viewport: CanvasViewport;
}

export interface CanvasProject extends CanvasDocument {
  id: string;
  name: string;
  asset_directory: string;
  created_at: number;
  updated_at: number;
}

export interface CanvasProjectSummary {
  id: string;
  name: string;
  asset_directory: string;
  created_at: number;
  updated_at: number;
}
