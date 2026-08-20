import {
  ImagePlus,
  LoaderCircle,
  RefreshCw,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import {
  bindSeedanceAnchorImage,
  composeSeedanceTasks,
  getSeedanceAnchorImagePreviews,
  getSeedanceGenerationReview,
  getSeedanceWorkspace,
  generateSeedanceAnchorImage,
  listArkFiles,
  refreshSeedanceTask,
  saveSeedanceWorkspace,
  submitSeedanceTask,
  uploadArkFile,
  type SeedanceWorkspaceInput,
} from "../../api/shotDetection";
import { publicErrorMessage } from "../../api/client";
import { Button } from "../../components/ui/Button";
import type {
  ArkFile,
  ReplacementCandidate,
  ReplicaPlaybookResult,
  SeedanceReferenceAsset,
  SeedanceReplacementBinding,
  SeedanceModelId,
  SeedanceAnchorImagePreview,
  SeedanceGenerationReviewSegment,
  SeedanceCompletedVideo,
  SeedanceVisualAnchor,
  SeedanceTask,
  StoryboardScriptResult,
} from "../../types/shotDetection";
import { formatShotTimestamp } from "./shotTime";
import {
  SeedanceTaskList,
  SegmentSubmitList,
} from "./SeedanceOperations";
import { GenerationReviewPackage } from "./GenerationReviewPackage";
import type { ReplacementWorkflowStep } from "./ReplacementWorkflowTabs";

interface ReplicaPlaybookPanelProps {
  activeStep: ReplacementWorkflowStep;
  onStepChange: (step: ReplacementWorkflowStep) => void;
  onUnlockStep: (step: ReplacementWorkflowStep) => void;
  result: ReplicaPlaybookResult;
  storyboardScript: StoryboardScriptResult | null;
  sourceAssetBaseUrl: string;
}
interface ReplacementBinding {
  enabled: boolean;
  targetDescription: string;
  assets: Array<SeedanceReferenceAsset | null>;
}
const MAX_REFERENCE_IMAGES = 3;
const DEFAULT_SEEDANCE_MODEL: SeedanceModelId =
  "doubao-seedance-2-0-mini-260615";
const SEEDANCE_MODEL_OPTIONS: Array<{
  value: SeedanceModelId;
  label: string;
  description: string;
}> = [
  { value: "doubao-seedance-2-0-mini-260615", label: "Seedance 2.0 Mini", description: "成本更低，适合先验证效果" },
  { value: "doubao-seedance-2-0-fast-260128", label: "Seedance 2.0 Fast", description: "生成更快，适合快速迭代" },
  { value: "doubao-seedance-2-0-260128", label: "Seedance 2.0 标准", description: "更适合最终成片" },
];

function referenceSlotLabel(type: ReplacementCandidate["type"], index: number) {
  return `${type === "product" ? "目标产品" : "目标对象"}参考图 ${index + 1}`;
}
function formatRanges(candidate: ReplacementCandidate) {
  return (candidate.time_ranges_ms ?? [])
    .map(
      ([start, end]) =>
        `${formatShotTimestamp(start / 1000)}–${formatShotTimestamp(end / 1000)}`,
    )
    .join("、");
}
function formatFileBytes(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(0, Math.ceil(bytes / 1024))} KB`;
}
function assetStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "等待处理",
    processing: "处理中",
    succeeded: "可用",
    uploaded: "已上传",
    failed: "处理失败",
  };
  return labels[status] ?? "状态更新中";
}
function isImageFile(file: ArkFile) {
  return file.mime_type.startsWith("image/") || /\.(png|jpe?g|webp|gif|heic)$/i.test(file.filename);
}
function normalizeBindings(
  bindings: Record<string, ReplacementBinding>,
): SeedanceReplacementBinding[] {
  return Object.entries(bindings).map(([candidateId, binding]) => ({
    candidate_id: candidateId,
    enabled: binding.enabled,
    target_description: binding.targetDescription,
    assets: binding.assets.flatMap((asset) => (asset ? [asset] : [])),
  }));
}
function restoreBindings(
  bindings: SeedanceReplacementBinding[],
): Record<string, ReplacementBinding> {
  return Object.fromEntries(
    bindings.map((binding) => {
      const assets: Array<SeedanceReferenceAsset | null> = Array.from(
        { length: MAX_REFERENCE_IMAGES },
        () => null,
      );
      binding.assets.forEach((asset) => {
        if (asset.slot_index >= 0 && asset.slot_index < MAX_REFERENCE_IMAGES)
          assets[asset.slot_index] = asset;
      });
      return [
        binding.candidate_id,
        {
          enabled: binding.enabled,
          targetDescription: binding.target_description ?? "",
          assets,
        },
      ];
    }),
  );
}
function hasReferenceImage(binding: ReplacementBinding | undefined) {
  return binding?.assets.some((asset) => Boolean(asset?.file_id)) ?? false;
}
interface ArkFilePickerProps {
  selectedId: string;
  files: ArkFile[];
  compact?: boolean;
  label: string;
  previewUrl?: string;
  uploading: boolean;
  onSelect: (file: ArkFile | null) => void;
  onUpload: (file: File) => void;
}
function ArkFilePicker({
  selectedId,
  files,
  compact,
  label,
  previewUrl,
  uploading,
  onSelect,
  onUpload,
}: ArkFilePickerProps) {
  const filtered = files.filter(isImageFile);
  const selected = filtered.find((file) => file.id === selectedId) ?? null;
  function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) onUpload(file);
  }
  return (
    <div
      className={`ark-file-picker${compact ? " ark-file-picker--compact" : ""}`}
    >
      {selected?.download_url || previewUrl ? (
        <img
          src={selected?.download_url || previewUrl}
          alt={selected?.filename || label}
        />
      ) : (
        <ImagePlus aria-hidden="true" size={compact ? 20 : 24} />
      )}
      <div className="ark-file-picker__details">
        <b>{selected ? selected.filename || "未命名测试素材" : label}</b>
        {selected ? (
          <>
            <span>
              {assetStatusLabel(selected.status)} · {formatFileBytes(selected.bytes)}
            </span>
            {selected.download_url ? (
              <a href={selected.download_url} target="_blank" rel="noreferrer">
                查看素材
              </a>
            ) : (
              <span className="ark-file-picker__no-url">
                素材仍在处理中
              </span>
            )}
          </>
        ) : (
          <span>
            上传图片，或从素材库中选择
          </span>
        )}
      </div>
      <div className="ark-file-picker__controls">
        <label className="ark-file-picker__upload">
          <Upload size={13} /> {uploading ? "上传中" : "上传"}
          <input
            type="file"
            accept="image/*"
            disabled={uploading}
            onChange={upload}
          />
        </label>
        <select
          value={selected?.id ?? ""}
          onChange={(event) =>
            onSelect(
              filtered.find((file) => file.id === event.target.value) ?? null,
            )
          }
          aria-label={`${label}：从素材库选择`}
        >
          <option value="">选择已有图片</option>
          {filtered.map((file) => (
            <option key={file.id} value={file.id}>
              {file.filename || "未命名素材"} · {assetStatusLabel(file.status)}
            </option>
          ))}
        </select>
        {selected ? (
          <button
            type="button"
            className="ark-file-picker__clear"
            onClick={() => onSelect(null)}
            aria-label={`移除${label}`}
          >
            <X size={14} />
          </button>
        ) : null}
      </div>
    </div>
  );
}

interface ReferenceImageUploaderProps {
  candidate: ReplacementCandidate;
  assets: Array<SeedanceReferenceAsset | null>;
  targetDescription: string;
  files: ArkFile[];
  localPreviews: Record<string, string>;
  uploadingSlot: string;
  onSelect: (index: number, file: ArkFile | null) => void;
  onUpload: (index: number, file: File) => void;
  onTargetDescriptionChange: (value: string) => void;
}
function ReferenceImageUploader({
  candidate,
  assets,
  files,
  localPreviews,
  uploadingSlot,
  onSelect,
  onUpload,
  targetDescription,
  onTargetDescriptionChange,
}: ReferenceImageUploaderProps) {
  const isProduct = candidate.type === "product";
  return (
    <div className="reference-image-uploader">
      <div className="reference-image-uploader__heading">
        <strong>{isProduct ? "产品参考图片" : "参考图片"}</strong>
        <span>最多 3 张 · 上传或从素材库选择</span>
      </div>
      <p>
        {isProduct
          ? "最多三张图共同描述同一个目标产品，可上传不同角度、状态或细节；系统不会猜测每张图的用途。"
          : "最多三张图共同描述同一个目标对象；只会替换当前勾选的对象。"}
      </p>
      <label className="reference-image-uploader__description">
        <span>目标{isProduct ? "产品" : "对象"}稳定特征（用于最终提示词）</span>
        <input
          value={targetDescription}
          onChange={(event) => onTargetDescriptionChange(event.target.value)}
          placeholder={
            isProduct
              ? "例如：白色圆润鸭形夜灯，橙色喙和双脚，胸前有白花"
              : "例如：短发女性，浅色针织衫，佩戴银色耳环"
          }
        />
      </label>
      <div className="reference-image-uploader__slots">
        {Array.from({ length: MAX_REFERENCE_IMAGES }, (_, index) => (
          <ArkFilePicker
            key={index}
            compact
            label={referenceSlotLabel(candidate.type, index)}
            selectedId={assets[index]?.file_id ?? ""}
            files={files}
            previewUrl={
              assets[index]?.file_id
                ? localPreviews[assets[index].file_id]
                : undefined
            }
            uploading={uploadingSlot === `${candidate.candidate_id}:${index}`}
            onSelect={(file) => onSelect(index, file)}
            onUpload={(file) => onUpload(index, file)}
          />
        ))}
      </div>
    </div>
  );
}

function SegmentAnchorStage({
  sourceAssetBaseUrl,
  segments,
  previews,
  anchors,
  files,
  confirmed,
  previewsLoading,
  generatingSegmentId,
  uploadingSlot,
  onConfirmedChange,
  onRefreshPreviews,
  onGenerate,
  onBind,
  onUpload,
}: {
  sourceAssetBaseUrl: string;
  segments: StoryboardScriptResult["segments"];
  previews: SeedanceAnchorImagePreview[];
  anchors: SeedanceVisualAnchor[];
  files: ArkFile[];
  confirmed: boolean;
  previewsLoading: boolean;
  generatingSegmentId: number | null;
  uploadingSlot: string;
  onConfirmedChange: (checked: boolean) => void;
  onRefreshPreviews: () => void;
  onGenerate: (segmentId: number, force: boolean) => void;
  onBind: (segmentId: number, file: ArkFile | null) => void;
  onUpload: (segmentId: number, file: File) => void;
}) {
  const bySegment = new Map(anchors.map((anchor) => [anchor.segment_id, anchor]));
  const shotCountBySegment = new Map(
    segments.map((segment) => [segment.segment_id, segment.storyboard.length]),
  );
  return (
    <section className="segment-anchor-stage">
      <div className="segment-anchor-stage__heading">
        <div>
          <h4>连续片段拼图替换 · 豆包 Seedream 5.0</h4>
          <p>
            每个连续片段最多 15 秒。系统会把多个关键帧合成一张锚点图，并调用豆包 Seedream 5.0 处理，用于保持替换后的商品在整段视频中一致。
          </p>
        </div>
        <Button
          variant="secondary"
          disabled={previewsLoading}
          onClick={onRefreshPreviews}
          icon={previewsLoading ? <LoaderCircle className="spin" /> : <RefreshCw />}
        >
          {previewsLoading ? "正在准备片段" : "准备片段锚点"}
        </Button>
      </div>
      <label className="segment-anchor-stage__confirm">
        <input checked={confirmed} onChange={(event) => onConfirmedChange(event.target.checked)} type="checkbox" />
        我确认仅在点击“生成锚点图”时调用豆包 Seedream 5.0 图片编辑并可能计费；上传或选择已有图片不计费。
      </label>
      {previews.length ? <ul className="segment-anchor-stage__list">
        {previews.map((preview) => {
          const anchor = bySegment.get(preview.segment_id);
          const file = files.find((item) => item.id === anchor?.anchor_file_id);
          const key = String(preview.segment_id);
          const isGenerating = generatingSegmentId === preview.segment_id;
          const needsRegeneration = anchor?.status === "succeeded" && !anchor.is_current;
          return (
            <li key={key}>
              <div className="segment-anchor-stage__summary">
                <div>
                  <b>连续片段 {String(preview.segment_id).padStart(2, "0")} · {shotCountBySegment.get(preview.segment_id) ?? 0} 个镜头完整合成 1 张图</b>
                  <span>
                    {formatShotTimestamp(preview.start_ms / 1000)}–{formatShotTimestamp(preview.end_ms / 1000)}
                  </span>
                  <small>{anchor ? needsRegeneration ? "旧版锚点图 · 需要按当前规则重新生成" : `${anchor.status === "uploaded" ? "手工锚点图" : "Seedream 5.0 锚点图"} · ${assetStatusLabel(anchor.status)}` : "尚未处理"}</small>
                  {file?.download_url ? (
                    <a href={file.download_url} target="_blank" rel="noreferrer">查看最终锚点图</a>
                  ) : null}
                  {anchor?.error_message ? <p>{publicErrorMessage(anchor.error_message, "图片处理失败，请稍后重试。")}</p> : null}
                </div>
                <details className="segment-anchor-stage__details">
                  <summary>查看拼图与处理详情</summary>
                  <div className="segment-anchor-stage__detail-grid">
                    <figure>
                      <figcaption>原始关键帧拼图</figcaption>
                      <img src={`${sourceAssetBaseUrl}/${preview.source_frame_path}`} alt={`分段 ${preview.segment_id} 的原始合并分镜图`} />
                    </figure>
                    <div className="segment-anchor-stage__prompt">
                      <b>{anchor?.status === "succeeded" && !needsRegeneration ? "本次使用的图片指令" : "图片处理指令"}</b>
                      {anchor?.status === "succeeded" && !needsRegeneration ? <pre>{anchor.prompt}</pre> : preview.ready ? <pre>{preview.prompt}</pre> : <p>{preview.message}</p>}
                    </div>
                    {file?.download_url ? <figure><figcaption>最终锚点图</figcaption><img src={file.download_url} alt={`分段 ${preview.segment_id} 的最终合并分镜锚点图`} /></figure> : null}
                  </div>
                </details>
              </div>
              <div className="segment-anchor-stage__actions">
                <Button
                  variant="secondary"
                  disabled={!confirmed || isGenerating}
                  onClick={() => onGenerate(preview.segment_id, anchor?.status === "succeeded")}
                  icon={isGenerating ? <LoaderCircle className="spin" /> : <ImagePlus />}
                >
                  {isGenerating ? "正在生成锚点图" : needsRegeneration ? "按当前规则重新生成" : anchor?.status === "succeeded" ? "重新生成锚点图" : "生成锚点图"}
                </Button>
                <ArkFilePicker
                  compact
                  label="或上传/选择手工处理合并图（会覆盖 AI 结果）"
                  selectedId={anchor?.status === "uploaded" ? anchor.anchor_file_id : ""}
                  files={files}
                  uploading={uploadingSlot === `anchor:${preview.segment_id}`}
                  onSelect={(file) => onBind(preview.segment_id, file)}
                  onUpload={(file) => onUpload(preview.segment_id, file)}
                />
              </div>
            </li>
          );
        })}
      </ul> : <p className="seedance-workbench__hint">点击“准备片段锚点”后，系统会列出每个连续片段；这一步不会调用图片模型。</p>}
    </section>
  );
}

export function ReplicaPlaybookPanel({
  activeStep,
  onStepChange,
  onUnlockStep,
  result,
  storyboardScript,
  sourceAssetBaseUrl,
}: ReplicaPlaybookPanelProps) {
  const playbook = result.playbook;
  const candidates = Array.isArray(playbook.replacement_candidates)
    ? playbook.replacement_candidates.filter((candidate) => candidate.type === "product")
    : [];
  const analysisId = result.analysis_id;
  const [bindings, setBindings] = useState<Record<string, ReplacementBinding>>(
    {},
  );
  const [arkFiles, setArkFiles] = useState<ArkFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [uploadingSlot, setUploadingSlot] = useState("");
  const [localPreviews, setLocalPreviews] = useState<Record<string, string>>(
    {},
  );
  const localPreviewsRef = useRef<Record<string, string>>({});
  const [extraInstruction, setExtraInstruction] = useState("");
  const [model, setModel] = useState<SeedanceModelId>(DEFAULT_SEEDANCE_MODEL);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [workspaceMessage, setWorkspaceMessage] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [workspaceSaving, setWorkspaceSaving] = useState(false);
  const [tasks, setTasks] = useState<SeedanceTask[]>([]);
  const [completedVideos, setCompletedVideos] = useState<SeedanceCompletedVideo[]>([]);
  const [anchors, setAnchors] = useState<SeedanceVisualAnchor[]>([]);
  const [anchorPreviews, setAnchorPreviews] = useState<SeedanceAnchorImagePreview[]>([]);
  const [anchorPreviewsLoading, setAnchorPreviewsLoading] = useState(false);
  const [generationReview, setGenerationReview] = useState<SeedanceGenerationReviewSegment[]>([]);
  const [generationReviewLoading, setGenerationReviewLoading] = useState(false);
  const [generatingAnchorSegmentId, setGeneratingAnchorSegmentId] = useState<number | null>(null);
  const [imageConfirmed, setImageConfirmed] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submittingSegmentId, setSubmittingSegmentId] = useState<number | null>(null);
  const [refreshingTaskId, setRefreshingTaskId] = useState("");
  const loadArkFiles = useCallback(async () => {
    if (!analysisId) return;
    setFilesLoading(true);
    try {
      setArkFiles((await listArkFiles(analysisId)).files);
    } catch (loadError) {
      setWorkspaceError(
        loadError instanceof Error ? loadError.message : "读取素材失败",
      );
    } finally {
      setFilesLoading(false);
    }
  }, [analysisId]);
  const persistWorkspace = useCallback(
    async (showMessage: boolean) => {
      if (!analysisId || !workspaceReady) return false;
      const payload: SeedanceWorkspaceInput = {
        model,
        extra_instruction: extraInstruction,
        bindings: normalizeBindings(bindings),
      };
      setWorkspaceSaving(true);
      setWorkspaceError("");
      try {
        const response = await saveSeedanceWorkspace(analysisId, payload);
        setTasks(response.tasks);
        setAnchors(response.anchors ?? []);
        setCompletedVideos(response.completed_videos ?? []);
        if (showMessage)
          setWorkspaceMessage("已保存素材绑定和补充要求；刷新页面后仍会保留。");
        return true;
      } catch (saveError) {
        setWorkspaceError(
          saveError instanceof Error ? saveError.message : "保存当前配置失败",
        );
      } finally {
        setWorkspaceSaving(false);
      }
      return false;
    },
    [analysisId, bindings, extraInstruction, model, workspaceReady],
  );
  useEffect(() => {
    if (!analysisId) {
      setWorkspaceReady(false);
      return;
    }
    let active = true;
    setWorkspaceReady(false);
    setWorkspaceError("");
    void getSeedanceWorkspace(analysisId)
      .then((workspaceResponse) => {
        if (!active) return;
        const workspace = workspaceResponse.workspace;
        setBindings(workspace ? restoreBindings(workspace.bindings) : {});
        setExtraInstruction(workspace?.extra_instruction ?? "");
        setModel(workspace?.model ?? DEFAULT_SEEDANCE_MODEL);
        setTasks(workspaceResponse.tasks);
        setAnchors(workspaceResponse.anchors ?? []);
        setCompletedVideos(workspaceResponse.completed_videos ?? []);
        setWorkspaceReady(true);
      })
      .catch((loadError) => {
        if (!active) return;
        setWorkspaceError(
          loadError instanceof Error ? loadError.message : "读取已保存配置失败",
        );
        setWorkspaceReady(true);
      });
    void listArkFiles(analysisId)
      .then((response) => {
        if (active) setArkFiles(response.files);
      })
      .catch((loadError) => {
        if (active)
          setWorkspaceError(
            loadError instanceof Error ? loadError.message : "读取素材失败",
          );
      });
    return () => {
      active = false;
    };
  }, [analysisId]);
  useEffect(() => {
    setGenerationReview([]);
  }, [bindings, extraInstruction, model]);
  useEffect(() => {
    if (!workspaceReady || !analysisId) return undefined;
    const timer = window.setTimeout(() => {
      void persistWorkspace(false);
    }, 900);
    return () => window.clearTimeout(timer);
  }, [
    analysisId,
    bindings,
    persistWorkspace,
    extraInstruction,
    model,
    workspaceReady,
  ]);
  useEffect(
    () => () => {
      Object.values(localPreviewsRef.current).forEach((url) =>
        URL.revokeObjectURL(url),
      );
    },
    [],
  );
  function updateBinding(
    candidateId: string,
    change: Partial<ReplacementBinding>,
  ) {
    setBindings((current) => ({
      ...current,
      [candidateId]: {
        enabled: current[candidateId]?.enabled ?? false,
        targetDescription: current[candidateId]?.targetDescription ?? "",
        assets:
          current[candidateId]?.assets ??
          Array.from({ length: MAX_REFERENCE_IMAGES }, () => null),
        ...change,
      },
    }));
  }
  function setReference(
    candidateId: string,
    index: number,
    file: ArkFile | null,
  ) {
    setBindings((current) => {
      const previous = current[candidateId] ?? {
        enabled: false,
        targetDescription: "",
        assets: Array.from({ length: MAX_REFERENCE_IMAGES }, () => null),
      };
      const assets = [...previous.assets];
      const candidate = candidates.find(
        (item) => item.candidate_id === candidateId,
      );
      assets[index] = file
        ? {
            slot_index: index,
            file_id: file.id,
            filename: file.filename,
            label: referenceSlotLabel(candidate?.type ?? "other", index),
          }
        : null;
      return { ...current, [candidateId]: { ...previous, assets } };
    });
  }
  async function upload(
    slot: string,
    file: File,
    onUploaded: (arkFile: ArkFile) => void,
  ) {
    const localPreview = file.type.startsWith("image/")
      ? URL.createObjectURL(file)
      : "";
    setUploadingSlot(slot);
    setWorkspaceError("");
    try {
      const arkFile = await uploadArkFile(analysisId, file);
      if (localPreview)
        setLocalPreviews((current) => {
          const oldPreview = current[arkFile.id];
          if (oldPreview) URL.revokeObjectURL(oldPreview);
          const next = { ...current, [arkFile.id]: localPreview };
          localPreviewsRef.current = next;
          return next;
        });
      setArkFiles((current) => [
        arkFile,
        ...current.filter((item) => item.id !== arkFile.id),
      ]);
      onUploaded(arkFile);
      setWorkspaceMessage(
        "素材已上传；图片可以立即预览，完成处理后即可提交生成。",
      );
    } catch (uploadError) {
      if (localPreview) URL.revokeObjectURL(localPreview);
      setWorkspaceError(
        uploadError instanceof Error ? uploadError.message : "上传素材失败",
      );
    } finally {
      setUploadingSlot("");
    }
  }
  async function refreshWorkspaceState() {
    try {
      const response = await getSeedanceWorkspace(analysisId);
      setTasks(response.tasks);
      setAnchors(response.anchors ?? []);
      setCompletedVideos(response.completed_videos ?? []);
    } catch {
      /* Keep the original action error when a background status refresh also fails. */
    }
  }
  async function refreshAnchorPreviews() {
    setAnchorPreviewsLoading(true);
    setWorkspaceError("");
    try {
      if (!(await persistWorkspace(false))) return;
      const response = await getSeedanceAnchorImagePreviews(analysisId);
      setAnchorPreviews(response.previews);
      setWorkspaceMessage("已准备连续片段锚点；尚未调用图片模型，不计费。");
    } catch (previewError) {
      setWorkspaceError(
        previewError instanceof Error ? previewError.message : "读取图片处理预览失败",
      );
    } finally {
      setAnchorPreviewsLoading(false);
    }
  }
  async function loadGenerationReview() {
    setGenerationReviewLoading(true);
    setWorkspaceError("");
    try {
      if (!(await persistWorkspace(false))) return;
      const response = await getSeedanceGenerationReview(analysisId);
      setGenerationReview(response.segments);
      setWorkspaceMessage("已准备可审查的片段视频、锚点图、商品参考图和最终指令；未调用模型，不计费。");
    } catch (instructionError) {
      setWorkspaceError(
        instructionError instanceof Error
          ? instructionError.message
          : "准备生成审查包失败",
      );
    } finally {
      setGenerationReviewLoading(false);
    }
  }
  async function submitTask(segmentId?: number) {
    setSubmitting(true);
    setSubmittingSegmentId(segmentId ?? null);
    setWorkspaceError("");
    try {
      if (!(await persistWorkspace(false))) return;
      const response = await submitSeedanceTask(analysisId, segmentId);
      setTasks(response.tasks);
      setAnchors(response.anchors ?? []);
      setCompletedVideos(response.completed_videos ?? []);
      setWorkspaceMessage(
        segmentId === undefined
          ? "已提交生成；可使用下方“刷新状态”查看结果。"
          : `分段 ${String(segmentId).padStart(2, "0")} 已独立提交；不会提交其他分段。`,
      );
      setConfirmed(false);
    } catch (submitError) {
      setWorkspaceError(
        submitError instanceof Error
          ? submitError.message
          : "提交生成失败",
      );
      await refreshWorkspaceState();
    } finally {
      setSubmitting(false);
      setSubmittingSegmentId(null);
    }
  }
  async function refreshTask(localTaskId: string) {
    setRefreshingTaskId(localTaskId);
    setWorkspaceError("");
    try {
      const response = await refreshSeedanceTask(analysisId, localTaskId);
      setTasks(response.tasks);
      setCompletedVideos(response.completed_videos ?? []);
    } catch (refreshError) {
      setWorkspaceError(
        refreshError instanceof Error ? refreshError.message : "刷新任务失败",
      );
      await refreshWorkspaceState();
    } finally {
      setRefreshingTaskId("");
    }
  }
  async function generateAnchor(segmentId: number, force: boolean) {
    setGeneratingAnchorSegmentId(segmentId);
    setWorkspaceError("");
    try {
      if (!(await persistWorkspace(false))) return;
      const response = await generateSeedanceAnchorImage(analysisId, segmentId, force);
      setTasks(response.tasks);
      setAnchors(response.anchors ?? []);
      await loadArkFiles();
      setWorkspaceMessage(`连续片段 ${String(segmentId).padStart(2, "0")} 的锚点图已生成。`);
    } catch (anchorError) {
      setWorkspaceError(anchorError instanceof Error ? anchorError.message : "生成分段视觉锚点图失败");
      await refreshWorkspaceState();
    } finally {
      setGeneratingAnchorSegmentId(null);
    }
  }
  async function bindAnchor(segmentId: number, file: ArkFile | null) {
    if (!file) return;
    setGeneratingAnchorSegmentId(segmentId);
    setWorkspaceError("");
    try {
      if (!(await persistWorkspace(false))) return;
      const response = await bindSeedanceAnchorImage(analysisId, segmentId, file.id);
      setAnchors(response.anchors ?? []);
      setWorkspaceMessage(`已将“${file.filename}”设为分段 ${String(segmentId).padStart(2, "0")} 的合并分镜锚点图。`);
    } catch (bindError) {
      setWorkspaceError(bindError instanceof Error ? bindError.message : "绑定分段视觉锚点图失败");
    } finally {
      setGeneratingAnchorSegmentId(null);
    }
  }
  async function uploadAnchor(segmentId: number, file: File) {
    await upload(`anchor:${segmentId}`, file, (arkFile) => {
      void bindAnchor(segmentId, arkFile);
    });
  }
  const hasReadyProduct = candidates.some(
    (candidate) =>
      bindings[candidate.candidate_id]?.enabled &&
      hasReferenceImage(bindings[candidate.candidate_id]),
  );
  const anchorsReady = Boolean(
    storyboardScript?.segments.length &&
      storyboardScript.segments.every((segment) =>
        anchors.some(
          (anchor) =>
            anchor.segment_id === segment.segment_id &&
            ["succeeded", "uploaded"].includes(anchor.status) &&
            anchor.is_current &&
            Boolean(anchor.anchor_file_id),
        ),
      ),
  );
  const allSegmentsCompleted = Boolean(
    storyboardScript?.segments.length &&
      storyboardScript.segments.every((segment) =>
        tasks.some(
          (task) => task.segment_id === segment.segment_id && task.status === "succeeded",
        ),
      ),
  );
  async function composeFinalVideo() {
    setSubmitting(true);
    setWorkspaceError("");
    try {
      const response = await composeSeedanceTasks(analysisId);
      setTasks(response.tasks);
      setAnchors(response.anchors ?? []);
      setCompletedVideos(response.completed_videos ?? []);
      setWorkspaceMessage("已合成完整成片，并保留原视频的人声和背景音乐。");
    } catch (composeError) {
      setWorkspaceError(
        composeError instanceof Error ? composeError.message : "合成成片失败",
      );
    } finally {
      setSubmitting(false);
    }
  }
  async function continueFromProducts() {
    if (!hasReadyProduct) {
      setWorkspaceError("请至少选择一个商品，并上传一张清晰的目标产品图。");
      return;
    }
    if (await persistWorkspace(true)) {
      onUnlockStep(3);
      onStepChange(3);
    }
  }
  function continueFromAnchors() {
    if (!anchorsReady) {
      setWorkspaceError("请为每个连续片段生成或上传一张最终锚点图后再继续。");
      return;
    }
    onUnlockStep(4);
    onStepChange(4);
  }
  return (
    <div className="replica-playbook replacement-workbench">
      {workspaceError ? <p className="shot-detection__message shot-detection__message--error" role="alert">{workspaceError}</p> : null}
      {activeStep === 2 ? (
        <>
          <section className="replacement-wizard__stage">
            <div className="replacement-wizard__stage-copy">
              <h4>选择需要替换的商品</h4>
              <p>勾选源视频里的商品，上传你的商品图。系统只改你选择的商品，人物、背景和镜头节奏保持不变。</p>
            </div>
            <div className="replacement-section-heading">
              <span>识别到 {candidates.length} 个可替换商品</span>
              <Button
                variant="text"
                disabled={filesLoading}
                onClick={() => void loadArkFiles()}
                icon={
                  filesLoading ? (
                    <LoaderCircle className="spin" />
                  ) : (
                    <RefreshCw />
                  )
                }
              >
                刷新素材库
              </Button>
            </div>
            {candidates.length ? (
              <ul className="replacement-candidate-list">
                {candidates.map((candidate, candidateIndex) => {
                  const binding = bindings[candidate.candidate_id];
                  const enabled = binding?.enabled ?? false;
                  return (
                    <li
                      className="replacement-candidate"
                      key={candidate.candidate_id}
                    >
                      <label className="replacement-candidate__toggle">
                        <input
                          type="checkbox"
                          checked={enabled}
                          onChange={(event) =>
                            updateBinding(candidate.candidate_id, {
                              enabled: event.target.checked,
                            })
                          }
                        />
                        <span>
                          <b>商品 {candidateIndex + 1}</b>
                          <small>出现时间 · {formatRanges(candidate) || "待确认"}</small>
                        </span>
                      </label>
                      <p>{candidate.source_description}</p>
                      {enabled ? (
                        <ReferenceImageUploader
                          candidate={candidate}
                          assets={binding?.assets ?? []}
                          targetDescription={binding?.targetDescription ?? ""}
                          files={arkFiles}
                          localPreviews={localPreviews}
                          uploadingSlot={uploadingSlot}
                          onSelect={(index, file) =>
                            setReference(candidate.candidate_id, index, file)
                          }
                          onUpload={(index, file) =>
                            void upload(
                              `${candidate.candidate_id}:${index}`,
                              file,
                              (arkFile) =>
                                setReference(
                                  candidate.candidate_id,
                                  index,
                                  arkFile,
                                ),
                            )
                          }
                          onTargetDescriptionChange={(value) =>
                            updateBinding(candidate.candidate_id, {
                              targetDescription: value,
                            })
                          }
                        />
                      ) : null}
                      {enabled && !hasReferenceImage(binding) ? (
                        <p className="replacement-candidate__warning">
                          请至少上传一张清晰的商品图。
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            ) : (
            <p>没有识别到稳定可替换的商品。请返回上一步重新分析，或更换参考视频。</p>
            )}
            <div className="replacement-wizard__footer">
              <Button variant="secondary" onClick={() => onStepChange(1)}>上一步</Button>
              <Button variant="primary" disabled={!hasReadyProduct || workspaceSaving} onClick={() => void continueFromProducts()}>{workspaceSaving ? "正在保存" : "保存并继续"}</Button>
            </div>
          </section>
        </>
      ) : null}
      {activeStep === 3 ? (
        <section className="replacement-wizard__stage">
          <div className="replacement-wizard__stage-copy">
            <h4>生成连续片段锚点</h4>
            <p>每个片段只处理一次关键帧拼图，不会逐镜头调用 AI。确认锚点图正确后，下一步生成整段视频。</p>
          </div>
          {storyboardScript ? (
            <SegmentAnchorStage
              sourceAssetBaseUrl={sourceAssetBaseUrl}
              segments={storyboardScript.segments}
              anchors={anchors}
              previews={anchorPreviews}
              files={arkFiles}
              confirmed={imageConfirmed}
              previewsLoading={anchorPreviewsLoading}
              generatingSegmentId={generatingAnchorSegmentId}
              uploadingSlot={uploadingSlot}
              onConfirmedChange={setImageConfirmed}
              onRefreshPreviews={() => void refreshAnchorPreviews()}
              onGenerate={(segmentId, force) => void generateAnchor(segmentId, force)}
              onBind={(segmentId, file) => void bindAnchor(segmentId, file)}
              onUpload={(segmentId, file) => void uploadAnchor(segmentId, file)}
            />
          ) : <p>连续片段尚未准备好，请返回第一步重新分析。</p>}
          <div className="replacement-wizard__footer">
            <Button variant="secondary" onClick={() => onStepChange(2)}>上一步</Button>
            <Button variant="primary" disabled={!anchorsReady} onClick={continueFromAnchors}>继续：检查并生成</Button>
          </div>
        </section>
      ) : null}
      {activeStep === 4 ? (
        <section className="replacement-wizard__stage">
          <div className="replacement-wizard__stage-copy">
            <h4>检查最终指令并生成</h4>
            <p>先查看每个连续片段的最终模型指令，确认后再提交生成。只有点击生成才会调用视频模型并可能产生费用。</p>
          </div>
          {!anchorsReady ? (
            <p className="shot-detection__message shot-detection__message--error">
              当前锚点图不是最新规则版本。请返回上一步，逐段点击“按当前规则重新生成”后再提交；这一步会调用图片模型并可能计费。
            </p>
          ) : null}
          <section className="seedance-workbench">
            <div className="seedance-workbench__heading">
              <div>
                <h4>当前配置</h4>
                <p>
                  商品图、锚点图和补充要求会自动保存。
                </p>
              </div>
            </div>
            <p className="seedance-workbench__hint">
              这些配置会自动保存；刷新页面后可以继续当前进度。
            </p>
            <label className="seedance-model-field">
              <span>生成模型</span>
              <select value={model} onChange={(event) => setModel(event.target.value as SeedanceModelId)} aria-label="选择视频生成模型">
                {SEEDANCE_MODEL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label} · {option.description}</option>)}
              </select>
            </label>
            <div className="seedance-workbench__actions">
              <span>{workspaceSaving ? "正在保存当前设置…" : "当前设置会自动保存"}</span>
              {workspaceMessage ? <span>{workspaceMessage}</span> : null}
            </div>
          </section>
          <section className="generation-instructions">
            <div className="generation-instructions__heading">
              <div>
                <h4>补充要求（可选）</h4>
                <p>商品、源商品描述、连续片段时间和参考图由后端模板注入。这里仅填写本项目额外要求，例如“产品始终保持亮灯”。</p>
              </div>
            </div>
            <textarea
              className="generation-instructions__editor"
              value={extraInstruction}
              onChange={(event) => setExtraInstruction(event.target.value)}
              spellCheck={false}
              aria-label="视频生成补充要求"
              placeholder="例如：产品在所有镜头中保持暖白色夜灯亮起；不要改变原视频节奏。"
            />
          </section>
          <section className="generation-instructions">
            <div className="generation-instructions__heading">
              <div>
                <h4>提交前审查</h4>
                <p>这里会展示每段实际上传的视频、最终锚点图、商品参考图和模型指令。准备素材不会调用模型或计费。</p>
              </div>
              <Button
                variant="text"
                disabled={generationReviewLoading}
                onClick={() => void loadGenerationReview()}
                icon={generationReviewLoading ? <LoaderCircle className="spin" /> : <RefreshCw />}
              >
                {generationReviewLoading ? "正在准备审查包" : "准备审查包"}
              </Button>
            </div>
            <GenerationReviewPackage segments={generationReview} />
          </section>
          <section className="seedance-submit">
            <h4>开始生成</h4>
            <p>
              系统会按连续片段生成：每段包含多个镜头，但只创建一个视频任务。只有点击生成才会产生费用。
            </p>
            {!anchorsReady ? (
              <div className="seedance-submit__blocked">
                <div>
                  <b>请先更新两个连续片段的锚点图</b>
                  <span>当前锚点来自旧规则，不能与新的“原视频＋锚点图＋商品参考图”提交方式混用。</span>
                </div>
                <Button variant="secondary" onClick={() => onStepChange(3)}>
                  去重新生成锚点
                </Button>
              </div>
            ) : null}
            <label>
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />{" "}
              我确认商品图、替换范围和镜头锚点无误，并同意本次调用可能计费。
            </label>
            {storyboardScript ? (
              <>
                <p className="seedance-submit__notice">
                  你可以一次生成全部 {storyboardScript.segments.length} 个连续片段，也可以在下方按需单独生成。
                </p>
                <Button
                  variant="primary"
                  disabled={submitting || !workspaceReady || !confirmed || !anchorsReady}
                  onClick={() => void submitTask()}
                  icon={submitting && submittingSegmentId === null ? <LoaderCircle className="spin" /> : <ImagePlus />}
                >
                  {submitting && submittingSegmentId === null
                    ? "正在创建生成任务"
                    : `生成全部 ${storyboardScript.segments.length} 个连续片段`}
                </Button>
                <Button
                  variant="text"
                  disabled={anchorPreviewsLoading}
                  onClick={() => void refreshAnchorPreviews()}
                  icon={anchorPreviewsLoading ? <LoaderCircle className="spin" /> : <RefreshCw />}
                >
                  {anchorPreviewsLoading ? "正在加载片段拼图提示词" : "加载片段拼图提示词"}
                </Button>
                <details className="seedance-submit__segments">
                  <summary>逐片段生成或重试</summary>
                <SegmentSubmitList
                  segments={storyboardScript.segments}
                  tasks={tasks}
                  anchorPreviews={anchorPreviews}
                  confirmed={confirmed}
                  submittingSegmentId={submittingSegmentId}
                  disabled={submitting || !workspaceReady || !anchorsReady}
                  onSubmit={(segmentId) => void submitTask(segmentId)}
                />
                </details>
              </>
            ) : null}
            <SeedanceTaskList
              tasks={tasks}
              refreshingTaskId={refreshingTaskId}
              onRefresh={(taskId) => void refreshTask(taskId)}
            />
            <section className="seedance-final-video">
              <div>
                <h5>导出与下载</h5>
                <p>保留四种可审查、可下载的文件：原参考视频、生成画面拼接版、最终合成版，以及原视频和最终合成版同步播放的左右对比预览。合成只使用本地 FFmpeg，不会调用视频模型或计费。</p>
              </div>
              <Button
                variant="secondary"
                disabled={!allSegmentsCompleted || submitting}
                onClick={() => void composeFinalVideo()}
              >
                {submitting ? "正在生成导出文件" : completedVideos.some((video) => video.kind === "comparison") ? "重新生成导出文件" : "生成四个导出文件"}
              </Button>
              {!allSegmentsCompleted ? <small>请先等待所有连续片段都显示“已完成”。</small> : null}
              {completedVideos.length ? (
                <div className="seedance-video-exports">
                  {completedVideos.map((video) => (
                    <article key={video.kind} className={`seedance-video-export${video.kind === "comparison" ? " seedance-video-export--comparison" : ""}`}>
                      <div>
                        <b>{video.label}</b>
                        <p>{video.description}</p>
                      </div>
                      <video controls preload="metadata" src={`${sourceAssetBaseUrl}/${video.asset_path}`}>
                        当前浏览器无法播放该视频。
                      </video>
                      <a href={`${sourceAssetBaseUrl}/${video.asset_path}`} download>
                        下载{video.label}
                      </a>
                    </article>
                  ))}
                </div>
              ) : null}
            </section>
          </section>
          <div className="replacement-wizard__footer">
            <Button variant="secondary" onClick={() => onStepChange(3)}>上一步</Button>
            <span>{workspaceSaving ? "正在保存当前设置…" : workspaceMessage || "当前设置会自动保存"}</span>
          </div>
        </section>
      ) : null}
    </div>
  );
}
