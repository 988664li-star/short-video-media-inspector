interface Shot {
  index: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  cut_score: number | null;
  clip: string;
  selected_frames: ShotFrame[];
}

interface ShotFrame {
  position: number;
  timestamp_seconds: number;
  path: string;
}

export interface ShotDetectionResult {
  aweme_id: string;
  duration_seconds: number;
  detector: string;
  scene_threshold: number;
  shots: Shot[];
  elapsed_seconds: number;
  cached: boolean;
  analysis_id: string;
  asset_base_url: string;
}

type ReplacementCandidateType =
  "person" | "product" | "background" | "screen" | "text" | "other";

export interface ReplacementCandidate {
  candidate_id: string;
  type: ReplacementCandidateType;
  source_description: string;
  scene_ids: number[];
  time_ranges_ms: [number, number][];
  replacement_reason: string;
  reference_requirements: string[];
  preserve_constraints: string[];
}

interface ReplicaPlaybook {
  source_summary?: string;
  global_preserve_constraints?: string[];
  replacement_candidates?: ReplacementCandidate[];
  data_gaps?: string[];
}

export interface ReplicaPlaybookResult {
  analysis_id: string;
  model: string;
  playbook: ReplicaPlaybook;
  cached: boolean;
}

export interface SeedanceReferenceAsset {
  slot_index: number;
  file_id: string;
  filename: string;
  label: string;
}

export type SeedanceModelId =
  | "doubao-seedance-2-0-mini-260615"
  | "doubao-seedance-2-0-260128"
  | "doubao-seedance-2-0-fast-260128";

export interface SeedanceReplacementBinding {
  candidate_id: string;
  enabled: boolean;
  target_description?: string;
  assets: SeedanceReferenceAsset[];
}

interface SeedanceWorkspace {
  analysis_id: string;
  model: SeedanceModelId;
  extra_instruction: string;
  bindings: SeedanceReplacementBinding[];
  version: number;
  updated_at: number;
}

export interface ArkFile {
  id: string;
  filename: string;
  mime_type: string;
  bytes: number;
  status: "processing" | "active" | "failed" | string;
  download_url: string;
  expire_at: number | null;
  created_at: number;
  error: Record<string, unknown>;
}

export interface SeedanceTask {
  local_task_id: string;
  provider_task_id: string | null;
  segment_id: number | null;
  segment_start_ms: number | null;
  segment_end_ms: number | null;
  model: string;
  status: string;
  request: Record<string, unknown>;
  response: Record<string, unknown>;
  error_message: string;
  created_at: number;
  updated_at: number;
}

export interface ArkApiEvent {
  id: number;
  operation: string;
  method: string;
  url: string;
  request: Record<string, unknown>;
  response: Record<string, unknown>;
  status_code: number | null;
  error_message: string;
  created_at: number;
}

export interface SeedanceWorkspaceResult {
  analysis_id: string;
  workspace: SeedanceWorkspace | null;
  tasks: SeedanceTask[];
  ark_events: ArkApiEvent[];
  anchors: SeedanceVisualAnchor[];
  completed_videos: SeedanceCompletedVideo[];
}

export interface SeedanceCompletedVideo {
  kind: "original" | "generated" | "combined" | "comparison";
  label: string;
  description: string;
  asset_path: string;
  bytes: number;
  updated_at: number;
}

export interface SeedanceVisualAnchor {
  segment_id: number;
  model: string;
  prompt: string;
  status: string;
  is_current: boolean;
  anchor_file_id: string;
  response: Record<string, unknown>;
  error_message: string;
  updated_at: number;
}

interface SeedanceAnchorImagePreviewInput {
  image_index: number;
  kind: "source_contact_sheet" | "target_product";
  label: string;
  source_frame_path?: string;
  candidate_id?: string;
  file_id?: string;
}

export interface SeedanceAnchorImagePreview {
  segment_id: number;
  start_ms: number;
  end_ms: number;
  source_frame_path: string;
  prompt: string;
  inputs: SeedanceAnchorImagePreviewInput[];
  ready: boolean;
  message: string;
  model: string;
}

export interface SeedanceAnchorImagePreviewResult {
  previews: SeedanceAnchorImagePreview[];
}

export interface SeedanceGenerationReviewProduct {
  candidate_id: string;
  target_description: string;
  assets: ArkFile[];
}

export interface SeedanceGenerationReviewSegment {
  segment_id: number;
  start_ms: number;
  end_ms: number;
  prompt: string;
  source_video: ArkFile;
  anchor_image: ArkFile;
  source_keyframe_image: ArkFile;
  product_references: SeedanceGenerationReviewProduct[];
}

export interface SeedanceGenerationReviewResult {
  segments: SeedanceGenerationReviewSegment[];
}

interface StoryboardScriptShot {
  order: number;
  time_range_ms: [number, number];
  title: string;
  scene_type: string;
  visual_description: string;
  action: string;
  shot_size: string;
  camera_angle: string;
  camera_motion: string;
  voiceover: string;
  shooting_notes: string;
}

interface StoryboardScriptSegment {
  segment_id: number;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  contact_sheet: string;
  segment_summary: string;
  storyboard: StoryboardScriptShot[];
  segment_script: string;
  usage?: Record<string, number>;
}

export interface StoryboardScriptResult {
  analysis_id: string;
  model: string;
  segments: StoryboardScriptSegment[];
  cached: boolean;
}

export interface SavedShotAnalysisState {
  detection: ShotDetectionResult;
  storyboard_script: StoryboardScriptResult | null;
  replica_playbook: ReplicaPlaybookResult | null;
}
