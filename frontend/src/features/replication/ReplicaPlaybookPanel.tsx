import {
  Check,
  ClipboardCopy,
  ImagePlus,
  LoaderCircle,
  RefreshCw,
  Replace,
  Save,
  Send,
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
  previewSeedanceRequest,
  refreshSeedanceTask,
  saveSeedanceWorkspace,
  submitSeedanceTask,
  uploadArkFile,
  type SeedanceWorkspaceInput,
} from "../../api/shotDetection";
import { Button } from "../../components/ui/Button";
import type {
  ArkApiEvent,
  ArkFile,
  ReplacementCandidate,
  ReplicaPlaybookResult,
  SeedanceReferenceAsset,
  SeedanceReplacementBinding,
  SeedanceModelId,
  SeedanceGenerationMode,
  SeedanceAnchorImagePreview,
  SeedanceRequestPlan,
  SeedanceVisualAnchor,
  SeedanceTask,
  StoryboardScriptResult,
} from "../../types/shotDetection";
import { formatShotTimestamp } from "./shotTime";

interface ReplicaPlaybookPanelProps {
  result: ReplicaPlaybookResult | null;
  storyboardScript: StoryboardScriptResult | null;
  sourceAssetBaseUrl: string;
  canBuild: boolean;
  loading: boolean;
  error: string;
  onBuild: () => void;
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
type FileKind = "image" | "video";

const MAX_REFERENCE_IMAGES = 3;
const DEFAULT_SEEDANCE_MODEL: SeedanceModelId =
  "doubao-seedance-2-0-mini-260615";
const DEFAULT_GENERATION_MODE: SeedanceGenerationMode = "segment_with_anchor";
const SEEDANCE_MODEL_OPTIONS: Array<{
  id: SeedanceModelId;
  name: string;
  note: string;
}> = [
  {
    id: "doubao-seedance-2-0-mini-260615",
    name: "Doubao Seedance 2.0 Mini",
    note: "成本优先；保留现有测试模型。",
  },
  {
    id: "doubao-seedance-2-0-fast-260128",
    name: "Doubao Seedance 2.0 Fast",
    note: "速度优先；使用同一提示词与同一素材作对比。",
  },
  {
    id: "doubao-seedance-2-0-260128",
    name: "Doubao Seedance 2.0",
    note: "旗舰模型；使用同一提示词与同一素材作对比。",
  },
];

function referenceSlotLabel(type: ReplacementCandidate["type"], index: number) {
  return `${type === "product" ? "目标产品" : "目标对象"}参考图 ${index + 1}`;
}
function candidateSubjectPrefix(type: ReplacementCandidate["type"]) {
  switch (type) {
    case "product":
      return "产品";
    case "person":
      return "人物";
    case "background":
      return "背景";
    case "screen":
      return "屏幕";
    case "text":
      return "文字";
    default:
      return "对象";
  }
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
function isFileKind(file: ArkFile, kind: FileKind) {
  return (
    file.mime_type.startsWith(`${kind}/`) ||
    (kind === "video"
      ? /\.(mp4|mov|webm)$/i
      : /\.(png|jpe?g|webp|gif|heic)$/i
    ).test(file.filename)
  );
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
      `${candidateSubjectPrefix(candidate.type)}${chineseLetter(ordinal)}`,
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
  kind: FileKind;
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
  kind,
  selectedId,
  files,
  compact,
  label,
  previewUrl,
  uploading,
  onSelect,
  onUpload,
}: ArkFilePickerProps) {
  const filtered = files.filter((file) => isFileKind(file, kind));
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
      {kind === "image" && (selected?.download_url || previewUrl) ? (
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
              {selected.status} · {formatFileBytes(selected.bytes)}
            </span>
            {selected.download_url ? (
              <a href={selected.download_url} target="_blank" rel="noreferrer">
                打开临时素材地址
              </a>
            ) : (
              <span className="ark-file-picker__no-url">
                暂未生成可访问地址
              </span>
            )}
          </>
        ) : (
          <span>
            上传本地{kind === "image" ? "图片" : "视频"}，或从测试素材库中选择
          </span>
        )}
      </div>
      <div className="ark-file-picker__controls">
        <label className="ark-file-picker__upload">
          <Upload size={13} /> {uploading ? "上传中" : "上传"}
          <input
            type="file"
            accept={
              kind === "image"
                ? "image/*"
                : "video/mp4,video/quicktime,video/webm"
            }
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
          aria-label={`${label}：选择方舟已有文件`}
        >
          <option value="">选择已有{kind === "image" ? "图片" : "视频"}</option>
          {filtered.map((file) => (
            <option key={file.id} value={file.id}>
              {file.filename || file.id} · {file.status}
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
        <span>最多 3 张 · 上传或选择测试素材库</span>
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
            kind="image"
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

function getOutputUrl(task: SeedanceTask) {
  const output = task.response.output;
  return output &&
    typeof output === "object" &&
    typeof (output as Record<string, unknown>).video_url === "string"
    ? ((output as Record<string, unknown>).video_url as string)
    : "";
}
function SeedanceTaskList({
  tasks,
  refreshingTaskId,
  onRefresh,
}: {
  tasks: SeedanceTask[];
  refreshingTaskId: string;
  onRefresh: (taskId: string) => void;
}) {
  if (!tasks.length)
    return (
      <p className="seedance-task-list__empty">
        尚未提交任何测试。上传文件、保存工作台和修改提示词都不会调用视频模型。
      </p>
    );
  return (
    <ul className="seedance-task-list">
      {tasks.map((task) => {
        const outputUrl = getOutputUrl(task);
        return (
          <li key={task.local_task_id}>
            <div>
              <b>{task.status}</b>
              {task.segment_id ? (
                <em>
                  分段 {String(task.segment_id).padStart(2, "0")}
                  {task.segment_start_ms !== null && task.segment_end_ms !== null
                    ? ` · ${formatShotTimestamp(task.segment_start_ms / 1000)}–${formatShotTimestamp(task.segment_end_ms / 1000)}`
                    : ""}
                </em>
              ) : null}
              <span>{new Date(task.created_at * 1000).toLocaleString()}</span>
            </div>
            <small>{task.provider_task_id ?? "等待方舟任务 ID"}</small>
            {outputUrl ? (
              <a href={outputUrl} target="_blank" rel="noreferrer">
                打开结果视频
              </a>
            ) : null}
            {task.error_message ? <p>{task.error_message}</p> : null}
            <Button
              variant="text"
              disabled={refreshingTaskId === task.local_task_id}
              onClick={() => onRefresh(task.local_task_id)}
              icon={
                refreshingTaskId === task.local_task_id ? (
                  <LoaderCircle className="spin" />
                ) : (
                  <RefreshCw />
                )
              }
            >
              刷新状态
            </Button>
          </li>
        );
      })}
    </ul>
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
                  <small>{anchor ? `${anchor.status === "uploaded" ? "手工锚点图" : anchor.model} · ${anchor.status}` : "尚未处理"}</small>
                  {file?.download_url ? (
                    <a href={file.download_url} target="_blank" rel="noreferrer">查看最终锚点图</a>
                  ) : null}
                  {anchor?.error_message ? <p>{anchor.error_message}</p> : null}
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
                          return <li key={`${input.image_index}:${input.file_id ?? input.source_frame_path ?? "source"}`}><code>{`图${input.image_index}`}</code>{input.kind === "source_contact_sheet" ? " 原始合并分镜图" : ` ${referenceFile?.filename ?? input.file_id ?? "目标产品参考图"}`}</li>;
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
                  kind="image"
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

function SeedanceRequestPreview({
  plan,
  previewing,
  onPreview,
  segments,
  selectedSegmentId,
  onSelectedSegmentChange,
  sourceVideo,
  referenceAssets,
}: {
  plan: SeedanceRequestPlan | null;
  previewing: boolean;
  onPreview: () => void;
  segments: StoryboardScriptResult["segments"];
  selectedSegmentId: number | null;
  onSelectedSegmentChange: (segmentId: number) => void;
  sourceVideo: ArkFile | undefined;
  referenceAssets: ReferenceAsset[];
}) {
  return (
    <section className="seedance-request-preview">
      <div className="seedance-request-preview__heading">
        <div>
          <h4>发送内容预览（不计费）</h4>
          <p>
            先保存当前输入，再按真实提交逻辑生成请求体和临时素材地址；不会调用
            Seedance 的生成接口。
          </p>
        </div>
        <Button
          variant="secondary"
          disabled={previewing}
          onClick={onPreview}
          icon={previewing ? <LoaderCircle className="spin" /> : <RefreshCw />}
        >
          {previewing ? "正在生成预览" : "保存并预览真实请求"}
        </Button>
      </div>
      {segments.length ? (
        <label className="seedance-request-preview__segment-picker">
          预览分段
          <select
            value={selectedSegmentId ?? segments[0].segment_id}
            onChange={(event) => onSelectedSegmentChange(Number(event.target.value))}
          >
            {segments.map((segment) => (
              <option key={segment.segment_id} value={segment.segment_id}>
                {`分段 ${String(segment.segment_id).padStart(2, "0")} · ${formatShotTimestamp(segment.start_ms / 1000)}–${formatShotTimestamp(segment.end_ms / 1000)}`}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <details className="seedance-request-preview__template">
        <summary>官方编辑提示词骨架</summary>
        <pre>{`将 @图片1 中的【目标产品的 2–3 个稳定特征】、@图片2 中的【同一产品的 2–3 个稳定特征】定义为产品A。严格编辑 @视频1，将其中的【旧对象】替换为产品A，动作和运镜不变。高清，画面稳定无变形，保持无字幕，不要生成水印，不要生成 Logo。`}</pre>
      </details>
      <div className="seedance-request-preview__mapping">
        <b>提示词引用与素材发送顺序</b>
        <ol>
          <li>
            <code>@视频1</code>
            <span>
              {plan?.mode === "segment_with_anchor"
                ? "对应分段的原视频 clip"
                : sourceVideo?.filename || "尚未选择原视频"}
            </span>
            <small>content 第 2 项（reference_video）</small>
          </li>
          {plan?.mode !== "segment_with_anchor" ? referenceAssets.map((asset, index) => (
            <li key={`${asset.candidateId}:${asset.slot_index}`}>
              <code>{`@图片${index + 1}`}</code>
              <span>{asset.filename || "未命名图片"}</span>
              <small>{`content 第 ${index + 3} 项（reference_image）`}</small>
            </li>
          )) : null}
          {plan?.mode === "segment_with_anchor" ? (
            <li>
              <code>@图片1…N</code>
              <span>该分段每个镜头各自确认过的最终锚点图</span>
              <small>按镜头时间顺序依次写入每个分段的 reference_image</small>
            </li>
          ) : null}
        </ol>
      </div>
      {plan ? (
        <>
          <p className="seedance-request-preview__mode">
            {plan.mode === "segment_with_anchor" ? `按 ${plan.segments.length} 个分段分别提交` : "整段视频提交"}
          </p>
          {plan.segments.map((item, index) => (
            <details className="seedance-request-preview__json" key={item.segment?.segment_id ?? index} open={plan.segments.length === 1}>
              <summary>
                {item.segment
                  ? `分段 ${String(item.segment.segment_id).padStart(2, "0")} · ${formatShotTimestamp(item.segment.start_ms / 1000)}–${formatShotTimestamp(item.segment.end_ms / 1000)}`
                  : "整段原视频"}
              </summary>
              <pre>{JSON.stringify(item.request, null, 2)}</pre>
            </details>
          ))}
        </>
      ) : (
        <p className="seedance-request-preview__empty">
          尚未生成预览。修改提示词、选择视频或图片后点击上方按钮，即可核对真实
          <code> content </code>顺序。
        </p>
      )}
    </section>
  );
}

function SegmentSubmitList({
  segments,
  tasks,
  confirmed,
  submittingSegmentId,
  disabled,
  onSubmit,
}: {
  segments: StoryboardScriptResult["segments"];
  tasks: SeedanceTask[];
  confirmed: boolean;
  submittingSegmentId: number | null;
  disabled: boolean;
  onSubmit: (segmentId: number) => void;
}) {
  return (
    <ul className="seedance-segment-submit-list">
      {segments.map((segment) => {
        const latestTask = tasks.find((task) => task.segment_id === segment.segment_id);
        const submitting = submittingSegmentId === segment.segment_id;
        return (
          <li key={segment.segment_id}>
            <div>
              <b>分段 {String(segment.segment_id).padStart(2, "0")}</b>
              <span>
                {formatShotTimestamp(segment.start_ms / 1000)}–{formatShotTimestamp(segment.end_ms / 1000)}
              </span>
              <small>
                {latestTask ? `最近任务：${latestTask.status}` : "尚未提交"}
              </small>
            </div>
            <Button
              variant="primary"
              disabled={disabled || !confirmed || submitting}
              onClick={() => onSubmit(segment.segment_id)}
              icon={submitting ? <LoaderCircle className="spin" /> : <Send />}
            >
              {submitting ? "正在提交" : `提交分段 ${String(segment.segment_id).padStart(2, "0")}`}
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

function ArkApiEventList({ events }: { events: ArkApiEvent[] }) {
  const seedanceEvents =
    events?.filter(
      (event) =>
        event.operation.startsWith("seedance.") ||
        event.operation.startsWith("seedream.") ||
        event.operation.startsWith("gpt-image."),
    ) ?? [];
  if (!seedanceEvents.length)
    return (
      <section className="ark-api-events">
        <h4>Seedance / GPT Image 调用详情</h4>
        <p>
          尚未向 Seedance 发出请求。文件上传和方舟 Files
          查询仅记录在服务端日志，不在这里干扰测试排查。
        </p>
      </section>
    );
  return (
    <section className="ark-api-events">
      <h4>Seedance / GPT Image 调用详情</h4>
      <p>
        这里展示实际请求体和方舟原始响应；鉴权头中的 API Key
        不会展示或写入日志。
      </p>
      <ul>
        {seedanceEvents.map((event) => (
          <li key={event.id}>
            <div>
              <b>{event.operation}</b>
              <span>
                {event.method} · {event.status_code ?? "未发出"} ·{" "}
                {new Date(event.created_at * 1000).toLocaleString()}
              </span>
            </div>
            <code>{event.url}</code>
            {event.error_message ? <p>{event.error_message}</p> : null}
            <details>
              <summary>请求参数</summary>
              <pre>{JSON.stringify(event.request, null, 2)}</pre>
            </details>
            <details>
              <summary>方舟返回</summary>
              <pre>{JSON.stringify(event.response, null, 2)}</pre>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReplicaPlaybookPanel({
  result,
  storyboardScript,
  sourceAssetBaseUrl,
  canBuild,
  loading,
  error,
  onBuild,
}: ReplicaPlaybookPanelProps) {
  const playbook = result?.playbook;
  const candidates = Array.isArray(playbook?.replacement_candidates)
    ? playbook.replacement_candidates
    : [];
  const analysisId = result?.analysis_id ?? "";
  const [bindings, setBindings] = useState<Record<string, ReplacementBinding>>(
    {},
  );
  const [sourceVideoFileId, setSourceVideoFileId] = useState("");
  const [model, setModel] = useState<SeedanceModelId>(
    DEFAULT_SEEDANCE_MODEL,
  );
  const [generationMode, setGenerationMode] = useState<SeedanceGenerationMode>(
    DEFAULT_GENERATION_MODE,
  );
  const [arkFiles, setArkFiles] = useState<ArkFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [uploadingSlot, setUploadingSlot] = useState("");
  const [localPreviews, setLocalPreviews] = useState<Record<string, string>>(
    {},
  );
  const localPreviewsRef = useRef<Record<string, string>>({});
  const [prompt, setPrompt] = useState("");
  const [promptEdited, setPromptEdited] = useState(false);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [workspaceMessage, setWorkspaceMessage] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [workspaceSaving, setWorkspaceSaving] = useState(false);
  const [tasks, setTasks] = useState<SeedanceTask[]>([]);
  const [anchors, setAnchors] = useState<SeedanceVisualAnchor[]>([]);
  const [anchorPreviews, setAnchorPreviews] = useState<SeedanceAnchorImagePreview[]>([]);
  const [anchorPreviewsLoading, setAnchorPreviewsLoading] = useState(false);
  const [generatingAnchorSegmentId, setGeneratingAnchorSegmentId] = useState<number | null>(null);
  const [arkEvents, setArkEvents] = useState<ArkApiEvent[]>([]);
  const [copied, setCopied] = useState(false);
  const [imageConfirmed, setImageConfirmed] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submittingSegmentId, setSubmittingSegmentId] = useState<number | null>(null);
  const [requestPreview, setRequestPreview] = useState<SeedanceRequestPlan | null>(null);
  const [previewSegmentId, setPreviewSegmentId] = useState<number | null>(null);
  const [previewingRequest, setPreviewingRequest] = useState(false);
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
        loadError instanceof Error ? loadError.message : "读取方舟素材失败",
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
        generation_mode: generationMode,
        source_video_file_id: sourceVideoFileId,
        prompt,
        bindings: normalizeBindings(bindings),
      };
      setWorkspaceSaving(true);
      setWorkspaceError("");
      try {
        const response = await saveSeedanceWorkspace(analysisId, payload);
        setTasks(response.tasks);
        setAnchors(response.anchors ?? []);
        setArkEvents(response.ark_events ?? []);
        if (showMessage)
          setWorkspaceMessage("已保存素材绑定和提示词；刷新页面后仍会保留。");
        return true;
      } catch (saveError) {
        setWorkspaceError(
          saveError instanceof Error ? saveError.message : "保存测试工作台失败",
        );
      } finally {
        setWorkspaceSaving(false);
      }
      return false;
    },
    [analysisId, bindings, generationMode, model, prompt, sourceVideoFileId, workspaceReady],
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
        setModel(workspace?.model ?? DEFAULT_SEEDANCE_MODEL);
        setGenerationMode(workspace?.generation_mode ?? DEFAULT_GENERATION_MODE);
        setSourceVideoFileId(workspace?.source_video_file_id ?? "");
        setPrompt(workspace?.prompt ?? "");
        setPromptEdited(Boolean(workspace?.prompt));
        setTasks(workspaceResponse.tasks);
        setAnchors(workspaceResponse.anchors ?? []);
        setArkEvents(workspaceResponse.ark_events ?? []);
        setWorkspaceReady(true);
      })
      .catch((loadError) => {
        if (!active) return;
        setWorkspaceError(
          loadError instanceof Error ? loadError.message : "读取测试工作台失败",
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
            loadError instanceof Error ? loadError.message : "读取方舟素材失败",
          );
      });
    return () => {
      active = false;
    };
  }, [analysisId]);
  useEffect(() => {
    if (workspaceReady && !promptEdited) setPrompt(generatedPrompt);
  }, [generatedPrompt, promptEdited, workspaceReady]);
  useEffect(() => {
    setRequestPreview(null);
  }, [bindings, generationMode, model, prompt, sourceVideoFileId]);
  useEffect(() => {
    if (!workspaceReady || !analysisId) return undefined;
    const timer = window.setTimeout(() => {
      void persistWorkspace(false);
    }, 900);
    return () => window.clearTimeout(timer);
  }, [
    analysisId,
    bindings,
    generationMode,
    model,
    persistWorkspace,
    prompt,
    sourceVideoFileId,
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
    setPromptEdited(false);
    setCopied(false);
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
    setPromptEdited(false);
    setCopied(false);
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
        "文件已上传到方舟；图片已在本地预览，状态为 processing 时暂不能提交生成。",
      );
    } catch (uploadError) {
      if (localPreview) URL.revokeObjectURL(localPreview);
      setWorkspaceError(
        uploadError instanceof Error ? uploadError.message : "上传方舟素材失败",
      );
    } finally {
      setUploadingSlot("");
    }
  }
  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  async function refreshArkEvents() {
    try {
      const response = await getSeedanceWorkspace(analysisId);
      setTasks(response.tasks);
      setAnchors(response.anchors ?? []);
      setArkEvents(response.ark_events ?? []);
    } catch {
      /* The original API error remains more useful than a follow-up refresh error. */
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
  async function previewRequest() {
    setPreviewingRequest(true);
    setWorkspaceError("");
    try {
      const selectedSegmentId =
        previewSegmentId ?? storyboardScript?.segments[0]?.segment_id ?? null;
      if (generationMode === "segment_with_anchor" && !selectedSegmentId) {
        setWorkspaceMessage("请先选择需要预览的分段。");
        return;
      }
      if (generationMode === "segment_with_anchor" && anchorPreviews.length) {
        const ready = new Set(
          anchors
            .filter((anchor) => ["succeeded", "uploaded"].includes(anchor.status) && anchor.anchor_file_id)
            .map((anchor) => anchor.segment_id),
        );
        const missing = anchorPreviews
          .filter((item) => item.segment_id === selectedSegmentId)
          .filter((item) => !ready.has(item.segment_id))
          .map((item) => String(item.segment_id).padStart(2, "0"));
        if (missing.length) {
          setWorkspaceMessage(
            `请先完成分段 ${missing.join("、")} 的合并分镜图片处理；锚点图成功后才能预览对应的 Seedance 视频请求。`,
          );
          return;
        }
      }
      if (!(await persistWorkspace(false))) return;
      const response = await previewSeedanceRequest(
        analysisId,
        generationMode === "segment_with_anchor" ? selectedSegmentId ?? undefined : undefined,
      );
      setRequestPreview(response.plan);
      setWorkspaceMessage(
        "已生成真实请求预览；尚未调用 Seedance，也不会计费。",
      );
    } catch (previewError) {
      setWorkspaceError(
        previewError instanceof Error
          ? previewError.message
          : "生成 Seedance 请求预览失败",
      );
    } finally {
      setPreviewingRequest(false);
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
      setArkEvents(response.ark_events ?? []);
      setWorkspaceMessage(
        segmentId === undefined
          ? "已提交到 Seedance；可使用下方“刷新状态”查看结果。"
          : `分段 ${String(segmentId).padStart(2, "0")} 已独立提交到 Seedance；不会提交其他分段。`,
      );
      setConfirmed(false);
    } catch (submitError) {
      setWorkspaceError(
        submitError instanceof Error
          ? submitError.message
          : "提交 Seedance 测试失败",
      );
      await refreshArkEvents();
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
      setArkEvents(response.ark_events ?? []);
    } catch (refreshError) {
      setWorkspaceError(
        refreshError instanceof Error ? refreshError.message : "刷新任务失败",
      );
      await refreshArkEvents();
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
      setArkEvents(response.ark_events ?? []);
      await loadArkFiles();
      setWorkspaceMessage(`分段 ${String(segmentId).padStart(2, "0")} 的 GPT Image 2 合并分镜锚点图已生成。`);
    } catch (anchorError) {
      setWorkspaceError(anchorError instanceof Error ? anchorError.message : "生成分段视觉锚点图失败");
      await refreshArkEvents();
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
      setArkEvents(response.ark_events ?? []);
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
      <div className="replica-tab-content__heading">
        <p>
          识别源视频中可替换的人物、产品、背景或屏幕内容；只为你上传或选择的方舟素材生成替换提示词。
        </p>
        <Button
          variant="primary"
          disabled={!canBuild || loading}
          onClick={onBuild}
          icon={loading ? <LoaderCircle className="spin" /> : <Replace />}
        >
          {loading ? "正在识别" : result ? "重新识别对象" : "识别替换对象"}
        </Button>
      </div>
      {!canBuild && !result ? (
        <p className="replica-tab-content__hint">请先完成“分段分镜脚本”。</p>
      ) : null}
      {error ? (
        <p
          className="shot-detection__message shot-detection__message--error"
          role="alert"
        >
          {error}
        </p>
      ) : null}
      {playbook ? (
        <div className="replica-playbook__scroll replacement-workbench">
          {playbook.source_summary ? (
            <section>
              <h4>源视频替换范围</h4>
              <p>{playbook.source_summary}</p>
            </section>
          ) : null}
          <section>
            <div className="replacement-section-heading">
              <h4>可替换对象</h4>
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
                刷新方舟素材
              </Button>
            </div>
            {candidates.length ? (
              <ul className="replacement-candidate-list">
                {candidates.map((candidate) => {
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
                          <b>{candidate.candidate_id}</b>
                          <small>
                            {candidate.type} · 镜头{" "}
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
                          请上传或选择 @图片1；未绑定时不会写入替换提示词。
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p>未识别到可靠的可替换对象。</p>
            )}
          </section>
          {generationMode === "segment_with_anchor" && storyboardScript ? (
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
                <h4>Seedance 2.0 模型对比工作台</h4>
                <p>
                  文件会上传至独立的测试素材桶，并生成短时有效的访问链接供
                  Seedance 调用。SQLite 仅保存素材绑定关系；不会修改现有业务桶。
                </p>
              </div>
            </div>
            <div className="seedance-workbench__model">
              <span>生成方式</span>
              <select
                aria-label="选择 Seedance 生成方式"
                value={generationMode}
                onChange={(event) => {
                  setGenerationMode(event.target.value as SeedanceGenerationMode);
                  setRequestPreview(null);
                  setWorkspaceMessage("");
                }}
              >
                <option value="segment_with_anchor">按分段：先图片替换，再视频编辑</option>
                <option value="whole_video">整段原视频编辑（旧测试方式）</option>
              </select>
              <small>
                {generationMode === "segment_with_anchor"
                  ? "复用已保存的分段分镜脚本。每段先生成一张产品已替换的视觉锚点图，再单独调用 Seedance。"
                  : "兼容原来的整段 Seedance 测试；不会使用图片锚点。"}
              </small>
            </div>
            {generationMode === "whole_video" ? (
              <ArkFilePicker
                kind="video"
                label="原视频（必填）"
                selectedId={sourceVideoFileId}
                files={arkFiles}
                uploading={uploadingSlot === "source"}
                onSelect={(file) => setSourceVideoFileId(file?.id ?? "")}
                onUpload={(file) =>
                  void upload("source", file, (arkFile) =>
                    setSourceVideoFileId(arkFile.id),
                  )
                }
              />
            ) : (
              <p className="seedance-workbench__hint">
                分段模式直接使用自动分镜时已保存的原视频和联系图，服务端会只上传对应分段到独立测试桶；无需再次上传整段原视频。
              </p>
            )}
            <div className="seedance-workbench__model">
              <span>测试模型</span>
              <select
                aria-label="选择 Seedance 测试模型"
                value={model}
                onChange={(event) => {
                  setModel(event.target.value as SeedanceModelId);
                  setRequestPreview(null);
                  setWorkspaceMessage("");
                }}
              >
                {SEEDANCE_MODEL_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </select>
              <code>{model}</code>
              <small>
                {
                  SEEDANCE_MODEL_OPTIONS.find((option) => option.id === model)
                    ?.note
                } 仅替换请求中的 model 字段；提示词、原视频、参考图、比例、时长、音频和水印参数均保持一致。
              </small>
            </div>
            <div className="seedance-workbench__actions">
              <Button
                variant="secondary"
                disabled={workspaceSaving || !workspaceReady}
                onClick={() => void persistWorkspace(true)}
                icon={
                  workspaceSaving ? <LoaderCircle className="spin" /> : <Save />
                }
              >
                {workspaceSaving ? "正在保存" : "保存工作台"}
              </Button>
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
          <section className="replacement-prompt">
            <div className="replacement-prompt__heading">
              <div>
                <h4>可编辑测试提示词</h4>
                <p>
                  编号严格按“提示词引用与素材发送顺序”对照：文本中的
                  <code>@视频1</code>、<code>@图片1</code>、<code>@图片2</code> 会对应
                  请求 <code>content</code> 数组中的同序素材。自动初稿采用“定义主体
                  A → 严格编辑 @视频1”的 sd2-pe 编辑句式，并挂载稳定、无字幕和无水印约束。
                  提交时只使用此文本框中的内容。
                </p>
              </div>
              <div className="replacement-prompt__buttons">
                <Button
                  variant="text"
                  onClick={() => {
                    setPrompt(generatedPrompt);
                    setPromptEdited(false);
                  }}
                  icon={<RefreshCw />}
                >
                  按 sd2-pe 优化提示词
                </Button>
                <Button
                  variant="secondary"
                  disabled={!prompt.trim()}
                  onClick={() => void copyPrompt()}
                  icon={copied ? <Check /> : <ClipboardCopy />}
                >
                  {copied ? "已复制" : "复制提示词"}
                </Button>
              </div>
            </div>
            <textarea
              className="replacement-prompt__editor"
              value={prompt}
              onChange={(event) => {
                setPrompt(event.target.value);
                setPromptEdited(true);
              }}
              spellCheck={false}
              aria-label="Seedance 测试提示词"
            />
          </section>
          <SeedanceRequestPreview
            plan={requestPreview}
            previewing={previewingRequest}
            onPreview={() => void previewRequest()}
            segments={generationMode === "segment_with_anchor" ? storyboardScript?.segments ?? [] : []}
            selectedSegmentId={previewSegmentId}
            onSelectedSegmentChange={(segmentId) => {
              setPreviewSegmentId(segmentId);
              setRequestPreview(null);
            }}
            sourceVideo={arkFiles.find((file) => file.id === sourceVideoFileId)}
            referenceAssets={referenceAssets}
          />
          <section className="seedance-submit">
            <h4>手动生成测试</h4>
            <p>
              只有这里点击提交，服务端才会向方舟创建视频任务并可能计费。系统不会自动重试或自动发起下一次测试。
            </p>
            <label>
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />{" "}
              我确认素材、提示词和模型无误，并同意本次调用可能计费。
            </label>
            {generationMode === "segment_with_anchor" && storyboardScript ? (
              <>
                <p className="seedance-submit__notice">
                  每次只能提交一个分段。点击分段 01 不会提交分段 02；每个按钮都会独立创建一条方舟任务并独立计费。
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
            ) : (
              <Button
                variant="primary"
                disabled={!confirmed || submitting || !workspaceReady}
                onClick={() => void submitTask()}
                icon={submitting ? <LoaderCircle className="spin" /> : <Send />}
              >
                {submitting ? "正在提交" : "提交 Seedance 测试"}
              </Button>
            )}
            <SeedanceTaskList
              tasks={tasks}
              refreshingTaskId={refreshingTaskId}
              onRefresh={(taskId) => void refreshTask(taskId)}
            />
            <ArkApiEventList events={arkEvents} />
          </section>
        </div>
      ) : !loading ? (
        <p className="replica-tab-content__empty">
          生成后将在这里列出可替换对象。
        </p>
      ) : null}
    </div>
  );
}
