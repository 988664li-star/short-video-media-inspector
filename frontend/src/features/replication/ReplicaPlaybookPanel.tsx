import {
  ImagePlus,
  LoaderCircle,
  RefreshCw,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import {
  bindSeedanceAnchorImage,
  getSeedanceAnchorImagePreviews,
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
  SeedanceVisualAnchor,
  SeedanceTask,
  StoryboardScriptResult,
} from "../../types/shotDetection";
import { formatShotTimestamp } from "./shotTime";
import {
  SeedanceTaskList,
  SegmentSubmitList,
} from "./SeedanceOperations";

interface ReplicaPlaybookPanelProps {
  result: ReplicaPlaybookResult;
  storyboardScript: StoryboardScriptResult | null;
  sourceAssetBaseUrl: string;
}
interface ReplacementBinding {
  enabled: boolean;
  targetDescription: string;
  assets: Array<SeedanceReferenceAsset | null>;
}
interface ReferenceAsset extends SeedanceReferenceAsset {
  candidateId: string;
  token: string;
}
const MAX_REFERENCE_IMAGES = 3;
const DEFAULT_SEEDANCE_MODEL: SeedanceModelId =
  "doubao-seedance-2-0-mini-260615";

function referenceSlotLabel(type: ReplacementCandidate["type"], index: number) {
  return `${type === "product" ? "目标产品" : "目标对象"}参考图 ${index + 1}`;
}
function chineseLetter(index: number) {
  return String.fromCodePoint("A".codePointAt(0)! + index);
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
function collectReferenceAssets(
  candidates: ReplacementCandidate[],
  bindings: Record<string, ReplacementBinding>,
) {
  const assets: ReferenceAsset[] = [];
  candidates.forEach((candidate) => {
    const binding = bindings[candidate.candidate_id];
    if (!binding?.enabled) return;
    binding.assets.forEach((asset, index) => {
      if (!asset?.file_id) return;
      assets.push({
        ...asset,
        candidateId: candidate.candidate_id,
        slot_index: index,
        token: `@图片${assets.length + 1}`,
      });
    });
  });
  return assets;
}

function createSd2PeVideoEditPrompt(
  candidates: ReplacementCandidate[],
  bindings: Record<string, ReplacementBinding>,
  referenceTokens: Map<string, string>,
) {
  const selected = candidates.filter(
    (candidate) =>
      bindings[candidate.candidate_id]?.enabled &&
      hasReferenceImage(bindings[candidate.candidate_id]),
  );
  if (!selected.length)
    return "请选择至少一个可替换对象，并上传或选择对应参考图；未绑定素材的对象保持源视频不变。";
  const typeCounts = new Map<ReplacementCandidate["type"], number>();
  const subjectNames = new Map<string, string>();
  selected.forEach((candidate) => {
    const ordinal = typeCounts.get(candidate.type) ?? 0;
    typeCounts.set(candidate.type, ordinal + 1);
    subjectNames.set(
      candidate.candidate_id,
      `商品${chineseLetter(ordinal)}`,
    );
  });
  const materialDefinitions = selected.map((candidate) => {
    const binding = bindings[candidate.candidate_id];
    const imageTokens = binding.assets.flatMap((asset, index) => {
      if (!asset?.file_id) return [];
      return [
        referenceTokens.get(`${candidate.candidate_id}:${index}`) ??
          `@图片${index + 1}`,
      ];
    });
    const targetDescription = binding.targetDescription.trim();
    const fallback = candidate.type === "product" ? "目标产品" : "目标对象";
    return `将${imageTokens.map((token) => `${token} 中展示的${targetDescription || fallback}`).join("、")}定义为${subjectNames.get(candidate.candidate_id)}。`;
  });
  const editCommands = selected.map(
    (candidate) =>
      `将其中的“${candidate.source_description}”替换为${subjectNames.get(candidate.candidate_id)}`,
  );
  const hasPerson = selected.some((candidate) => candidate.type === "person");
  return `${materialDefinitions.join(" ")} 严格编辑 @视频1，${editCommands.join("；")}，保持原视频的动作和运镜不变，未提及部分保持不变。高清，细节丰富，电影质感，色彩自然，光影柔和；${hasPerson ? "人物面部稳定不变形、五官清晰，" : "画面稳定无变形，"}动作连贯自然，不僵硬，无穿模无卡顿；保持无字幕，不要生成水印，不要生成 Logo。`;
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
  referenceTokens: Array<string | undefined>;
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
  referenceTokens,
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
            label={`${referenceTokens[index] ?? `@图片${index + 1}`} · ${referenceSlotLabel(candidate.type, index)}`}
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
  return (
    <section className="segment-anchor-stage">
      <div className="segment-anchor-stage__heading">
        <div>
          <h4>图片锚点处理</h4>
          <p>
            这是独立的 GPT Image 2 分段合并图编辑步骤，不会生成视频。每个不超过 15 秒的分段，将其多个镜头合并图只处理一次，得到一张“产品已替换正确”的分段锚点图；也可上传或选择你手工处理好的合并图覆盖结果。确认图片正确后，下一步视频模型只使用该分段锚点图。
          </p>
        </div>
        <Button
          variant="secondary"
          disabled={previewsLoading}
          onClick={onRefreshPreviews}
          icon={previewsLoading ? <LoaderCircle className="spin" /> : <RefreshCw />}
        >
          {previewsLoading ? "正在读取处理细节" : "刷新图片处理预览"}
        </Button>
      </div>
      <label className="segment-anchor-stage__confirm">
        <input checked={confirmed} onChange={(event) => onConfirmedChange(event.target.checked)} type="checkbox" />
        我确认仅在点击“GPT Image 2 编辑”时调用图片模型并可能计费；上传或选择已有图片不计费。
      </label>
      {previews.length ? <ul className="segment-anchor-stage__list">
        {previews.map((preview) => {
          const anchor = bySegment.get(preview.segment_id);
          const file = files.find((item) => item.id === anchor?.anchor_file_id);
          const key = String(preview.segment_id);
          const isGenerating = generatingSegmentId === preview.segment_id;
          return (
            <li key={key}>
              <div className="segment-anchor-stage__summary">
                <div>
                  <b>分段 {String(preview.segment_id).padStart(2, "0")} · 合并分镜图</b>
                  <span>
                    {formatShotTimestamp(preview.start_ms / 1000)}–{formatShotTimestamp(preview.end_ms / 1000)}
                  </span>
                  <small>{anchor ? `${anchor.status === "uploaded" ? "手工锚点图" : "AI 锚点图"} · ${assetStatusLabel(anchor.status)}` : "尚未处理"}</small>
                  {file?.download_url ? (
                    <a href={file.download_url} target="_blank" rel="noreferrer">查看最终锚点图</a>
                  ) : null}
                  {anchor?.error_message ? <p>{publicErrorMessage(anchor.error_message, "图片处理失败，请稍后重试。")}</p> : null}
                </div>
                <div className="segment-anchor-stage__detail-grid">
                  <figure>
                    <figcaption>图1 · 原始合并分镜图（将被编辑）</figcaption>
                    <img
                      src={`${sourceAssetBaseUrl}/${preview.source_frame_path}`}
                      alt={`分段 ${preview.segment_id} 的原始合并分镜图`}
                    />
                  </figure>
                  <div className="segment-anchor-stage__prompt">
                    <b>{anchor?.status === "succeeded" ? "本次生成实际使用的图片提示词" : "将发送给图片模型的提示词"}</b>
                    {anchor?.status === "succeeded" ? <pre>{anchor.prompt}</pre> : preview.ready ? <pre>{preview.prompt}</pre> : <p>{preview.message}</p>}
                    {preview.inputs.length ? (
                      <ol>
                        {preview.inputs.map((input) => {
                          const referenceFile = input.file_id ? files.find((item) => item.id === input.file_id) : undefined;
                          return <li key={`${input.image_index}:${input.file_id ?? input.source_frame_path ?? "source"}`}><code>{`图${input.image_index}`}</code>{input.kind === "source_contact_sheet" ? " 原始合并分镜图" : ` ${referenceFile?.filename ?? "目标产品参考图"}`}</li>;
                        })}
                      </ol>
                    ) : null}
                  </div>
                  {file?.download_url ? (
                    <figure>
                      <figcaption>最终锚点图（视频阶段将使用）</figcaption>
                      <img src={file.download_url} alt={`分段 ${preview.segment_id} 的最终合并分镜锚点图`} />
                    </figure>
                  ) : null}
                </div>
              </div>
              <div className="segment-anchor-stage__actions">
                <Button
                  variant="secondary"
                  disabled={!confirmed || isGenerating}
                  onClick={() => onGenerate(preview.segment_id, anchor?.status === "succeeded")}
                  icon={isGenerating ? <LoaderCircle className="spin" /> : <ImagePlus />}
                >
                  {isGenerating ? "正在编辑图片" : anchor?.status === "succeeded" ? "重新编辑图片" : "GPT Image 2 编辑"}
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
      </ul> : <p className="seedance-workbench__hint">点击“刷新图片处理预览”后，系统会列出每个分段的原始合并分镜图及精确编辑提示词；不调用图片模型。</p>}
    </section>
  );
}

export function ReplicaPlaybookPanel({
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
  const [prompt, setPrompt] = useState("");
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [workspaceMessage, setWorkspaceMessage] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [workspaceSaving, setWorkspaceSaving] = useState(false);
  const [tasks, setTasks] = useState<SeedanceTask[]>([]);
  const [anchors, setAnchors] = useState<SeedanceVisualAnchor[]>([]);
  const [anchorPreviews, setAnchorPreviews] = useState<SeedanceAnchorImagePreview[]>([]);
  const [anchorPreviewsLoading, setAnchorPreviewsLoading] = useState(false);
  const [generatingAnchorSegmentId, setGeneratingAnchorSegmentId] = useState<number | null>(null);
  const [imageConfirmed, setImageConfirmed] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submittingSegmentId, setSubmittingSegmentId] = useState<number | null>(null);
  const [refreshingTaskId, setRefreshingTaskId] = useState("");
  const referenceAssets = useMemo(
    () => collectReferenceAssets(candidates, bindings),
    [bindings, candidates],
  );
  const referenceTokens = useMemo(
    () =>
      new Map(
        referenceAssets.map((asset) => [
          `${asset.candidateId}:${asset.slot_index}`,
          asset.token,
        ]),
      ),
    [referenceAssets],
  );
  const generatedPrompt = useMemo(
    () => createSd2PeVideoEditPrompt(candidates, bindings, referenceTokens),
    [bindings, candidates, referenceTokens],
  );
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
        model: DEFAULT_SEEDANCE_MODEL,
        prompt,
        bindings: normalizeBindings(bindings),
      };
      setWorkspaceSaving(true);
      setWorkspaceError("");
      try {
        const response = await saveSeedanceWorkspace(analysisId, payload);
        setTasks(response.tasks);
        setAnchors(response.anchors ?? []);
        if (showMessage)
          setWorkspaceMessage("已保存素材绑定和提示词；刷新页面后仍会保留。");
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
    [analysisId, bindings, prompt, workspaceReady],
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
        setPrompt(workspace?.prompt ?? "");
        setTasks(workspaceResponse.tasks);
        setAnchors(workspaceResponse.anchors ?? []);
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
    if (workspaceReady) setPrompt(generatedPrompt);
  }, [generatedPrompt, workspaceReady]);
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
    prompt,
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
      setWorkspaceMessage("已读取图片处理的原图、素材顺序和精确提示词；未调用图片模型，不计费。");
    } catch (previewError) {
      setWorkspaceError(
        previewError instanceof Error ? previewError.message : "读取图片处理预览失败",
      );
    } finally {
      setAnchorPreviewsLoading(false);
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
      setWorkspaceMessage(`分段 ${String(segmentId).padStart(2, "0")} 的 GPT Image 2 合并分镜锚点图已生成。`);
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
  return (
    <div className="replica-tab-content replica-playbook">
      <div className="replica-playbook__scroll replacement-workbench">
          {playbook.source_summary ? (
            <section>
              <h4>源视频替换范围</h4>
              <p>{playbook.source_summary}</p>
            </section>
          ) : null}
          <section>
            <div className="replacement-section-heading">
              <h4>确认要替换的商品</h4>
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
                          <small>
                            镜头{" "}
                            {(candidate.scene_ids ?? [])
                              .map((id) => String(id).padStart(2, "0"))
                              .join("、") || "待确认"}{" "}
                            · {formatRanges(candidate) || "待确认"}
                          </small>
                        </span>
                      </label>
                      <p>{candidate.source_description}</p>
                      <p className="replacement-candidate__reason">
                        {candidate.replacement_reason}
                      </p>
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
                          referenceTokens={Array.from(
                            { length: MAX_REFERENCE_IMAGES },
                            (_, index) =>
                              referenceTokens.get(
                                `${candidate.candidate_id}:${index}`,
                              ),
                          )}
                        />
                      ) : null}
                      {enabled && !hasReferenceImage(binding) ? (
                        <p className="replacement-candidate__warning">
                          请上传至少一张商品图；未绑定素材时不会生成替换片段。
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            ) : (
            <p>未识别到可稳定替换的商品。建议更换参考视频，或重新识别镜头。</p>
            )}
          </section>
          {storyboardScript ? (
            <SegmentAnchorStage
              sourceAssetBaseUrl={sourceAssetBaseUrl}
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
          ) : null}
          <section className="seedance-workbench">
            <div className="seedance-workbench__heading">
              <div>
                <h4>准备逐镜头生成</h4>
                <p>
                  你确认商品图和镜头锚点后，系统会为每个镜头单独生成，方便逐段检查效果。
                </p>
              </div>
            </div>
            <p className="seedance-workbench__hint">
              商品图、镜头锚点和生成要求会自动保存。当前使用固定生成配置，避免同一项目因模型切换产生不一致结果。
            </p>
            <div className="seedance-workbench__actions">
              <span>{workspaceSaving ? "正在保存当前设置…" : "当前设置会自动保存"}</span>
              {workspaceMessage ? <span>{workspaceMessage}</span> : null}
            </div>
            {workspaceError ? (
              <p
                className="shot-detection__message shot-detection__message--error"
                role="alert"
              >
                {workspaceError}
              </p>
            ) : null}
          </section>
          <section className="seedance-submit">
            <h4>提交生成</h4>
            <p>
              只有点击提交才会创建视频生成任务并可能计费。系统不会自动重试或自动发起下一次生成。
            </p>
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
                  每次只能提交一个分段。点击分段 01 不会提交分段 02；每个分段会独立创建任务并独立计费。
                </p>
                <SegmentSubmitList
                  segments={storyboardScript.segments}
                  tasks={tasks}
                  confirmed={confirmed}
                  submittingSegmentId={submittingSegmentId}
                  disabled={submitting || !workspaceReady}
                  onSubmit={(segmentId) => void submitTask(segmentId)}
                />
              </>
            ) : null}
            <SeedanceTaskList
              tasks={tasks}
              refreshingTaskId={refreshingTaskId}
              onRefresh={(taskId) => void refreshTask(taskId)}
            />
          </section>
      </div>
    </div>
  );
}
