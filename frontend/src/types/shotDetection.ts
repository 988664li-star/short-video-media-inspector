export interface Shot {
  index: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  cut_score: number | null;
  clip: string;
  selected_frames: ShotFrame[];
}

export interface ShotFrame {
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

export interface SceneVisualAnalysis {
  scene_id: number;
  scene_type: string;
  visual_subject: string[];
  action: string;
  shot_size: string;
  camera_angle: string;
  camera_motion: string;
  scene_description: string;
  conversion_purpose: string;
  evidence: string[];
  usage?: Record<string, number>;
}

export interface SceneVisualAnalysisResult {
  analysis_id: string;
  model: string;
  scene_analyses: SceneVisualAnalysis[];
  cached: boolean;
}

export interface ReplicaContentStage {
  stage: string;
  scene_ids: number[];
  time_range_ms: [number, number];
  strategy: string;
  evidence: string[];
}

export interface ReplicaShot {
  scene_id: number;
  duration_ms: number;
  scene_function: string;
  shooting_direction: string;
  voiceover_strategy: string;
  editing_direction: string;
  must_preserve: string[];
  adaptable_variables: string[];
}

export interface ReplicaPlaybook {
  video_positioning?: string;
  content_structure?: ReplicaContentStage[];
  replica_shots?: ReplicaShot[];
  replication_formula?: string[];
  production_checklist?: string[];
  data_gaps?: string[];
}

export interface ReplicaPlaybookResult {
  analysis_id: string;
  model: string;
  playbook: ReplicaPlaybook;
  cached: boolean;
}
