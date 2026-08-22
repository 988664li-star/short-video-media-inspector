import {
  CheckCircle2,
  Image as ImageIcon,
  Link2,
  LoaderCircle,
  PencilLine,
  Plus,
  Send,
  Trash2,
  WandSparkles,
} from "lucide-react";
import type { NodeProps } from "@xyflow/react";
import { useState } from "react";

import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeShell } from "./CanvasNodeShell";
import type { CanvasFlowNode } from "./flowTypes";

const SHOT_PREVIEW_LIMIT = 6;

function kindLabel(kind: string) {
  return { product: "商品", person: "人物", background: "背景", text: "文字", other: "对象" }[kind] || "对象";
}

function promptStatus(status: string) {
  return {
    pending: "待生成提示词",
    ready: "待提交",
    queued: "排队中",
    running: "生成中",
    succeeded: "已完成",
    failed: "失败",
  }[status] || status;
}

export function ReplacementTaskNode({ id, data, selected }: NodeProps<CanvasFlowNode>) {
  const {
    buildReplacementPrompts,
    addTargetImageNode,
    getCanvasNode,
    previewMedia,
    submitReplacementTasks,
    toggleReplacementShot,
    updateOperation,
    updateReplacementShotPrompt,
    updateReplacementTask,
    videoModels,
  } = useCanvasNodeActions();
  const { node } = data;
  const task = node.replacement_task;
  const [showAllPrompts, setShowAllPrompts] = useState(false);
  const [showAllShots, setShowAllShots] = useState(false);
  const [editingShotIndex, setEditingShotIndex] = useState<number | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const sourceGroup = getCanvasNode(task?.shot_collection_node_id);
  const outputGroup = getCanvasNode(task?.output_shot_collection_node_id);
  const selectedShotIds = new Set(task?.selected_shot_indices ?? []);

  if (!task) return null;
  const subjectBindings = task.subjects.map((subject, subjectIndex) => ({
    subject,
    subjectIndex,
    targetImage: getCanvasNode(subject.target_node_id),
  }));
  const visibleSubjectBindings = subjectBindings;
  const allSubjectsReady = subjectBindings.length > 0 && subjectBindings.every(({ targetImage }) => (
    targetImage?.kind === "image" && targetImage.asset_id && targetImage.asset_url
  ));
  const unreadySubjectBindings = subjectBindings.filter(({ targetImage }) => (
    targetImage?.kind !== "image" || !targetImage.asset_id || !targetImage.asset_url
  ));
  const taskName = task.subjects.map((subject) => subject.source_object_name).join(" + ");
  const allShots = sourceGroup?.shot_assets?.filter((shot) => task.shot_indices.includes(shot.index)) ?? [];
  const visibleShots = showAllShots ? allShots : allShots.slice(0, SHOT_PREVIEW_LIMIT);
  const selectedPrompts = task.shot_prompts.filter((item) => selectedShotIds.has(item.shot_index));
  const prompts = showAllPrompts ? selectedPrompts : selectedPrompts.slice(0, 3);
  const generatedVersions = (outputGroup?.shot_assets ?? []).flatMap((shot) => shot.replacement_versions ?? [])
    .filter((version) => version.task_node_id === id);
  const outputVersionByShot = new Map((outputGroup?.shot_assets ?? []).map((shot) => [
    shot.index,
    shot.replacement_versions?.find((version) => version.task_node_id === id),
  ]));
  const readyCount = selectedPrompts.filter((item) => (
    item.status === "ready" && !outputVersionByShot.get(item.shot_index)
  )).length;
  const activeCount = generatedVersions.filter((version) => version.status === "queued" || version.status === "running").length;
  const completedCount = generatedVersions.filter((version) => version.status === "succeeded").length;
  const isBusy = node.operation?.status === "running";
  const requiresPromptRebuild = selectedPrompts.some((item) => item.input_revision !== 3);
  const availableModels = videoModels.filter((model) => model.capabilities.includes("subject_replace"));
  const selectedModel = node.operation?.model || availableModels[0]?.id || "";
  const selectedModelIsAvailable = availableModels.some((model) => model.id === selectedModel);

  const removeSubjects = (sourceObjectIds: Set<string>) => {
    const subjects = task.subjects.filter((subject) => !sourceObjectIds.has(subject.source_object_id));
    if (!subjects.length) return;
    const shotIndices = [...new Set(subjects.flatMap((subject) => subject.shot_indices))].sort((left, right) => left - right);
    const primarySubject = subjects[0];
    updateReplacementTask(id, {
      source_object_id: primarySubject.source_object_id,
      source_object_kind: primarySubject.source_object_kind,
      source_object_name: primarySubject.source_object_name,
      source_object_description: primarySubject.source_object_description,
      target_description: primarySubject.target_description,
      subjects,
      shot_indices: shotIndices,
      actions: primarySubject.actions,
      selected_shot_indices: task.selected_shot_indices.filter((shotIndex) => shotIndices.includes(shotIndex)),
      // Removing a subject changes every affected edit instruction. Rebuild them
      // instead of allowing a stale prompt to be submitted.
      shot_prompts: task.shot_prompts.map((item) => ({
        shot_index: item.shot_index,
        prompt: "",
        input_revision: 0,
        status: "pending" as const,
      })),
    });
  };

  return (
    <CanvasNodeShell node={node} selected={selected} label="视频主体替换" icon={<WandSparkles />}>
      <section className="canvas-replacement-task nodrag nowheel">
        <header className="canvas-replacement-task__summary">
          <div><span>{task.subjects.length > 1 ? "多主体一次替换" : `${kindLabel(task.source_object_kind)}主体替换`}</span><strong>{taskName}</strong></div>
          <p>已选 {task.selected_shot_indices.length}/{task.shot_indices.length} 个连续片段</p>
        </header>

        <section className="canvas-replacement-task__shots" aria-label="选择需要替换的连续编辑片段">
          <header>
            <strong>替换范围</strong>
            <div>
              <span>只提交已勾选片段</span>
              <button
                type="button"
                title={task.selected_shot_indices.length === allShots.length ? "取消选择全部相关片段" : "选择全部相关片段"}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={() => updateReplacementTask(id, {
                  selected_shot_indices: task.selected_shot_indices.length === allShots.length ? [] : allShots.map((shot) => shot.index),
                })}
              >{task.selected_shot_indices.length === allShots.length ? "取消全选" : `全选 ${allShots.length} 个片段`}</button>
            </div>
          </header>
          <div className="canvas-replacement-task__shot-grid">
            {visibleShots.map((shot) => <div key={shot.asset_id} className={`canvas-replacement-task__shot ${selectedShotIds.has(shot.index) ? "is-selected" : ""}`}>
              <input aria-label={`片段 ${String(shot.index).padStart(2, "0")}`} type="checkbox" checked={selectedShotIds.has(shot.index)} onPointerDown={(event) => event.stopPropagation()} onChange={() => toggleReplacementShot(id, shot.index)} />
              <video src={shot.asset_url} muted playsInline preload="metadata" onClick={() => previewMedia({
                ...node, kind: "video", title: `编辑片段 ${String(shot.index).padStart(2, "0")}`,
                detail: `${shot.start_seconds.toFixed(2)}–${shot.end_seconds.toFixed(2)} 秒`, asset_id: shot.asset_id, asset_url: shot.asset_url, asset_name: shot.asset_name,
              })} />
              <span>片段 {String(shot.index).padStart(2, "0")}</span>
            </div>)}
          </div>
          {allShots.length > SHOT_PREVIEW_LIMIT ? <button type="button" className="canvas-replacement-task__show-all" onClick={() => setShowAllShots((current) => !current)}>
            {showAllShots ? "收起片段" : `查看全部 ${allShots.length} 个相关片段`}
          </button> : null}
          <p>每一项都是独立的完整视频编辑任务；勾选多个片段仅是批量提交，不会把多个片段一起送给模型。</p>
        </section>

        <section className="canvas-replacement-task__bindings">
          <header>
            <strong><Link2 /> 主体与目标图一对一绑定</strong>
            <div className="canvas-replacement-task__binding-status">
              <span>{subjectBindings.filter(({ targetImage }) => targetImage?.asset_id && targetImage.asset_url).length}/{subjectBindings.length} 已就绪</span>
              {unreadySubjectBindings.length ? <button
                type="button"
                className="canvas-replacement-task__remove-unready"
                onClick={() => removeSubjects(new Set(unreadySubjectBindings.map(({ subject }) => subject.source_object_id)))}
              ><Trash2 /> 移除未就绪主体（{unreadySubjectBindings.length}）</button> : null}
            </div>
          </header>
          {visibleSubjectBindings.map(({ subject, subjectIndex, targetImage }) => <article key={subject.source_object_id} className={`canvas-replacement-task__binding ${targetImage?.asset_id ? "is-ready" : ""}`}>
            <div className="canvas-replacement-task__binding-source">
              <small>源主体 {subjectIndex + 1}</small>
              <strong>{subject.source_object_name}</strong>
              <span>{kindLabel(subject.source_object_kind)}</span>
              {task.subjects.length > 1 ? <button
                type="button"
                className="canvas-replacement-task__remove-subject"
                onClick={() => removeSubjects(new Set([subject.source_object_id]))}
              ><Trash2 /> 移除主体</button> : null}
            </div>
            <span className="canvas-replacement-task__binding-arrow">替换为</span>
            <div className="canvas-replacement-task__binding-target">
              {targetImage?.asset_id && targetImage.asset_url ? <button type="button" title={`预览：${targetImage.asset_name || targetImage.title}`} onClick={() => previewMedia(targetImage)}>
                <img src={targetImage.asset_url} alt={targetImage.asset_name || targetImage.title} />
              </button> : <ImageIcon />}
              <div>
                <strong>{targetImage?.asset_name || `目标${kindLabel(subject.source_object_kind)}图片`}</strong>
                <button type="button" onClick={() => addTargetImageNode(id, subject.source_object_id)}>
                  {targetImage?.asset_id ? "查看图片节点" : targetImage ? "上传或生成图片" : <><Plus /> 创建图片节点</>}
                </button>
              </div>
            </div>
            <label>
              <span>目标说明（选填）</span>
              <input
                className="nodrag nowheel"
                value={subject.target_description}
                placeholder="描述该目标的外观、颜色、材质与结构"
                onPointerDown={(event) => event.stopPropagation()}
                onPointerMove={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
                onChange={(event) => {
                  const subjects = task.subjects.map((item) => item.source_object_id === subject.source_object_id
                    ? { ...item, target_description: event.target.value }
                    : item);
                  updateReplacementTask(id, {
                    subjects,
                    target_description: subjects[0]?.target_description ?? "",
                  });
                }}
              />
            </label>
          </article>)}
          {!visibleSubjectBindings.length ? <p>还没有可替换主体。</p> : null}
          <p>每个源主体只使用右侧绑定的目标图；多个主体会在同一个视频任务中一次完成替换。</p>
        </section>

        <div className="canvas-replacement-task__submit-row">
          <label title="视频主体替换使用视频编辑模型">
            <span>视频模型</span>
            <select disabled={!availableModels.length} value={selectedModel} onChange={(event) => updateOperation(id, { model: event.target.value, status: "idle", error: "" })}>
              {selectedModel && !selectedModelIsAvailable ? <option value={selectedModel}>{selectedModel}</option> : null}
              {availableModels.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
              {!availableModels.length ? <option value="">没有可用模型</option> : null}
            </select>
          </label>
          <button className="canvas-replacement-task__build" type="button" disabled={!allSubjectsReady || !task.selected_shot_indices.length || isBusy} onClick={() => void buildReplacementPrompts(id)}>
            {isBusy ? <LoaderCircle className="spin" /> : <WandSparkles />} 生成视频编辑指令
          </button>
        </div>
        {!allSubjectsReady ? <p className="canvas-replacement-task__hint"><ImageIcon /> 请先为每个主体上传一张对应目标图，缺少任意一张都不会提交。</p> : null}
        <p className="canvas-replacement-task__hint">每个连续片段只提交一个完整视频任务：原视频片段 + 全部已绑定目标图，在一次生成中同时替换。</p>

        <div className="canvas-replacement-task__prompts">
          <header><strong>逐片段视频编辑指令</strong><span>{readyCount} 条待提交 · {activeCount} 条生成中 · {completedCount} 条完成</span></header>
          <p className="canvas-replacement-task__prompt-hint"><PencilLine /> 点击“编辑提示词”查看、修改并单独生成当前完整片段。</p>
          {requiresPromptRebuild ? <p className="canvas-replacement-task__error">此任务使用的是旧生成结构。请先点击“生成视频编辑指令”后再提交。</p> : null}
          {prompts.map((item) => {
            const outputVersion = outputVersionByShot.get(item.shot_index);
            const outputIsActive = outputVersion?.status === "pending"
              || outputVersion?.status === "queued"
              || outputVersion?.status === "running";
            const canSubmit = Boolean(item.prompt.trim())
              && item.input_revision === 3
              && !outputIsActive
              && (item.status === "ready" || outputVersion?.status === "failed" || outputVersion?.status === "succeeded");
            return <article key={item.shot_index} className={`canvas-replacement-task__prompt ${editingShotIndex === item.shot_index ? "is-editing" : ""}`}>
              <header>
                <span>片段 {String(item.shot_index).padStart(2, "0")}</span>
                <small>{promptStatus(outputVersion?.status ?? item.status)}</small>
                <div className="canvas-replacement-task__prompt-actions">
                  <button
                    className="canvas-replacement-task__edit-prompt"
                    type="button"
                    aria-expanded={editingShotIndex === item.shot_index}
                    title="展开提示词编辑区"
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={() => setEditingShotIndex((current) => current === item.shot_index ? null : item.shot_index)}
                  ><PencilLine /> {editingShotIndex === item.shot_index ? "收起" : "编辑提示词"}</button>
                  <button
                    className="canvas-replacement-task__quick-submit"
                    type="button"
                    title={confirmed ? "只提交当前完整片段的视频编辑任务" : "请先勾选下方的费用确认后提交"}
                    disabled={!confirmed || !canSubmit || isBusy}
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={() => void submitReplacementTasks(id, item.shot_index)}
                  ><Send /> {outputVersion?.status === "succeeded" ? "重新生成" : "生成片段"}</button>
                </div>
              </header>
              {editingShotIndex === item.shot_index ? <div className="canvas-replacement-task__prompt-editor">
                <label>
                  <span>视频编辑提示词</span>
                  <textarea
                    className="nodrag nowheel"
                    rows={9}
                    value={item.prompt}
                    placeholder="生成后可审核并修改此镜头的视频编辑指令…"
                    onPointerDown={(event) => event.stopPropagation()}
                    onPointerMove={(event) => event.stopPropagation()}
                    onMouseDown={(event) => event.stopPropagation()}
                    onKeyDown={(event) => event.stopPropagation()}
                    onChange={(event) => updateReplacementShotPrompt(id, item.shot_index, event.target.value)}
                  />
                </label>
                <footer>
                  <span>修改后自动保存；确认无误再单独提交。</span>
                  <button
                    className="canvas-replacement-task__single-submit"
                    type="button"
                    title="只提交当前片段；修改提示词后可用它重新生成该片段"
                    disabled={!confirmed || !canSubmit || isBusy}
                    onClick={() => void submitReplacementTasks(id, item.shot_index)}
                  ><Send /> {outputVersion?.status === "succeeded" ? "重新生成" : "生成片段"} {String(item.shot_index).padStart(2, "0")}</button>
                </footer>
              </div> : null}
              {outputVersion?.error || item.error ? <p className="canvas-replacement-task__error">{outputVersion?.error || item.error}</p> : null}
            </article>;
          })}
          {selectedPrompts.length > 3 ? <button className="canvas-replacement-task__show-all" type="button" onClick={() => setShowAllPrompts((current) => !current)}>
            {showAllPrompts ? "收起其余片段" : `查看全部 ${selectedPrompts.length} 个已选片段`}
          </button> : null}
        </div>

        <label className="canvas-replacement-task__confirm">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
          我已审核目标素材、替换范围和视频编辑指令，确认提交视频生成可能产生费用。
        </label>
        <div className="canvas-replacement-task__actions">
          <button type="button" className="canvas-replacement-task__generate" disabled={!confirmed || !readyCount || isBusy} onClick={() => void submitReplacementTasks(id)}>
            <Send /> 提交 {readyCount} 个完整视频编辑任务
          </button>
        </div>
        {node.operation?.error ? <p className="canvas-replacement-task__error" role="alert">{node.operation.error}</p> : null}
        {node.operation?.status === "succeeded" && node.operation.message ? <p className="canvas-replacement-task__success"><CheckCircle2 /> {node.operation.message}</p> : null}
      </section>
    </CanvasNodeShell>
  );
}
