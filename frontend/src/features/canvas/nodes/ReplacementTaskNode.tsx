import {
  CheckCircle2,
  Image as ImageIcon,
  Layers3,
  Link2,
  LoaderCircle,
  PencilLine,
  Plus,
  RefreshCw,
  Send,
  WandSparkles,
} from "lucide-react";
import type { NodeProps } from "@xyflow/react";
import { useMemo, useState } from "react";

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
    composeReplacementTask,
    addTargetImageNode,
    getCanvasNode,
    getUpstreamNodes,
    previewMedia,
    refreshReplacementTasks,
    submitReplacementTasks,
    toggleReplacementShot,
    updateOperation,
    updateReplacementShotPrompt,
    updateReplacementTask,
  } = useCanvasNodeActions();
  const { node } = data;
  const task = node.replacement_task;
  const [showAllPrompts, setShowAllPrompts] = useState(false);
  const [showAllShots, setShowAllShots] = useState(false);
  const [editingShotIndex, setEditingShotIndex] = useState<number | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const upstream = getUpstreamNodes(id);
  const targetImages = useMemo(() => upstream
    .filter((upstreamNode) => upstreamNode.kind === "image" && upstreamNode.asset_id && upstreamNode.asset_url), [upstream]);
  const sourceGroup = upstream.find((upstreamNode) => upstreamNode.kind === "shot_collection");
  const outputGroup = getCanvasNode(task?.output_shot_collection_node_id);
  const selectedShotIds = new Set(task?.selected_shot_indices ?? []);

  if (!task) return null;
  const allShots = sourceGroup?.shot_assets?.filter((shot) => task.shot_indices.includes(shot.index)) ?? [];
  const visibleShots = showAllShots ? allShots : allShots.slice(0, SHOT_PREVIEW_LIMIT);
  const selectedPrompts = task.shot_prompts.filter((item) => selectedShotIds.has(item.shot_index));
  const prompts = showAllPrompts ? selectedPrompts : selectedPrompts.slice(0, 3);
  const readyCount = selectedPrompts.filter((item) => item.status === "ready").length;
  const activeCount = selectedPrompts.filter((item) => item.status === "queued" || item.status === "running").length;
  const completedCount = selectedPrompts.filter((item) => item.status === "succeeded").length;
  const hasRefreshableTasks = selectedPrompts.some((item) => item.provider_task_id && (item.status === "queued" || item.status === "running"));
  const generatedVersions = (outputGroup?.shot_assets ?? []).flatMap((shot) => shot.replacement_versions ?? [])
    .filter((version) => version.task_node_id === id);
  const canCompose = generatedVersions.length > 0
    && generatedVersions.every((version) => version.status === "succeeded" || version.status === "failed");
  const isBusy = node.operation?.status === "running";

  return (
    <CanvasNodeShell node={node} selected={selected} label="镜头替换任务" icon={<WandSparkles />}>
      <section className="canvas-replacement-task nodrag nowheel">
        <header className="canvas-replacement-task__summary">
          <div><span>{kindLabel(task.source_object_kind)}替换</span><strong>{task.source_object_name}</strong></div>
          <p>已选 {task.selected_shot_indices.length}/{task.shot_indices.length} 镜头</p>
        </header>

        <section className="canvas-replacement-task__shots" aria-label="选择需要替换的镜头">
          <header>
            <strong>替换范围</strong>
            <div>
              <span>只提交已勾选镜头</span>
              <button
                type="button"
                title={task.selected_shot_indices.length === allShots.length ? "取消选择全部相关镜头" : "选择全部相关镜头"}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={() => updateReplacementTask(id, {
                  selected_shot_indices: task.selected_shot_indices.length === allShots.length ? [] : allShots.map((shot) => shot.index),
                })}
              >{task.selected_shot_indices.length === allShots.length ? "取消全选" : `全选 ${allShots.length} 个镜头`}</button>
            </div>
          </header>
          <div className="canvas-replacement-task__shot-grid">
            {visibleShots.map((shot) => <div key={shot.asset_id} className={`canvas-replacement-task__shot ${selectedShotIds.has(shot.index) ? "is-selected" : ""}`}>
              <input aria-label={`镜头 ${String(shot.index).padStart(2, "0")}`} type="checkbox" checked={selectedShotIds.has(shot.index)} onPointerDown={(event) => event.stopPropagation()} onChange={() => toggleReplacementShot(id, shot.index)} />
              <video src={shot.asset_url} muted playsInline preload="metadata" onClick={() => previewMedia({
                ...node, kind: "video", title: `镜头 ${String(shot.index).padStart(2, "0")}`,
                detail: `${shot.start_seconds.toFixed(2)}–${shot.end_seconds.toFixed(2)} 秒`, asset_id: shot.asset_id, asset_url: shot.asset_url, asset_name: shot.asset_name,
              })} />
              <span>镜头 {String(shot.index).padStart(2, "0")}</span>
            </div>)}
          </div>
          {allShots.length > SHOT_PREVIEW_LIMIT ? <button type="button" className="canvas-replacement-task__show-all" onClick={() => setShowAllShots((current) => !current)}>
            {showAllShots ? "收起镜头" : `查看全部 ${allShots.length} 个相关镜头`}
          </button> : null}
          <p>每一项都是独立的视频任务；勾选多个镜头仅是批量提交，不会把多个镜头一起送给模型。</p>
        </section>

        <div className="canvas-replacement-task__materials">
          <span><Link2 /> 目标素材</span>
          {targetImages.length ? <div>
            {targetImages.map((image) => <button key={image.id} type="button" title={`预览：${image.asset_name || image.title}`} onClick={() => previewMedia(image)}>
              <img src={image.asset_url} alt={image.asset_name || image.title} />
            </button>)}
          </div> : <div className="canvas-replacement-task__empty-material">
            <p>还没有目标素材</p>
            <button type="button" onClick={() => addTargetImageNode(id)}><Plus /> 添加目标图片</button>
          </div>}
        </div>

        <label className="canvas-replacement-task__target-description">
          <span>目标{kindLabel(task.source_object_kind)}说明</span>
          <input
            value={task.target_description}
            placeholder="描述外观、颜色、材质、结构；商品图仍是最高依据"
            onKeyDown={(event) => event.stopPropagation()}
            onChange={(event) => updateReplacementTask(id, { target_description: event.target.value })}
          />
        </label>

        <div className="canvas-replacement-task__submit-row">
          <label title="逐镜头替换使用视频编辑模型">
            <span>视频模型</span>
            <select value={node.operation?.model || "doubao-seedance-2-0-mini-260615"} onChange={(event) => updateOperation(id, { model: event.target.value, status: "idle", error: "" })}>
              <option value="doubao-seedance-2-0-mini-260615">Seedance 2.0 Mini</option>
              <option value="doubao-seedance-2-0-260128">Seedance 2.0</option>
              <option value="doubao-seedance-2-0-fast-260128">Seedance 2.0 Fast</option>
            </select>
          </label>
          <button className="canvas-replacement-task__build" type="button" disabled={!targetImages.length || !task.selected_shot_indices.length || isBusy} onClick={() => void buildReplacementPrompts(id)}>
            {isBusy ? <LoaderCircle className="spin" /> : <WandSparkles />} 生成镜头提示词
          </button>
        </div>
        {!targetImages.length ? <p className="canvas-replacement-task__hint"><ImageIcon /> 添加图片会创建独立图片节点；你也可以连接已有目标素材。</p> : null}

        <div className="canvas-replacement-task__prompts">
          <header><strong>逐镜头视频指令</strong><span>{readyCount} 条待提交 · {completedCount} 条完成</span></header>
          <p className="canvas-replacement-task__prompt-hint"><PencilLine /> 点击“编辑提示词”查看、修改并单独生成当前镜头。</p>
          {prompts.map((item) => (
            <article key={item.shot_index} className={`canvas-replacement-task__prompt ${editingShotIndex === item.shot_index ? "is-editing" : ""}`}>
              <header>
                <span>镜头 {String(item.shot_index).padStart(2, "0")}</span>
                <small>{promptStatus(item.status)}</small>
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
                    title={confirmed ? "只提交当前镜头的视频替换任务" : "请先勾选下方的费用确认后提交"}
                    disabled={!confirmed || item.status !== "ready" || isBusy}
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={() => void submitReplacementTasks(id, item.shot_index)}
                  ><Send /> 生成镜头</button>
                </div>
              </header>
              {editingShotIndex === item.shot_index ? <div className="canvas-replacement-task__prompt-editor">
                <label>
                  <span>Seedance 视频提示词</span>
                  <textarea rows={9} value={item.prompt} placeholder="生成后可审核并修改此镜头的 Seedance 视频指令…" onKeyDown={(event) => event.stopPropagation()} onChange={(event) => updateReplacementShotPrompt(id, item.shot_index, event.target.value)} />
                </label>
                <footer>
                  <span>修改后自动保存；确认无误再单独提交。</span>
                  <button
                    className="canvas-replacement-task__single-submit"
                    type="button"
                    title="只提交当前镜头；修改提示词后可用它重新生成该镜头"
                    disabled={!confirmed || item.status !== "ready" || isBusy}
                    onClick={() => void submitReplacementTasks(id, item.shot_index)}
                  ><Send /> 生成镜头 {String(item.shot_index).padStart(2, "0")}</button>
                </footer>
              </div> : null}
              {item.error ? <p className="canvas-replacement-task__error">{item.error}</p> : null}
            </article>
          ))}
          {selectedPrompts.length > 3 ? <button className="canvas-replacement-task__show-all" type="button" onClick={() => setShowAllPrompts((current) => !current)}>
            {showAllPrompts ? "收起其余镜头" : `查看全部 ${selectedPrompts.length} 个已选镜头`}
          </button> : null}
        </div>

        <label className="canvas-replacement-task__confirm">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
          我已审核目标素材、替换范围和镜头指令，确认提交视频生成可能产生费用。
        </label>
        <div className="canvas-replacement-task__actions">
          <button type="button" className="canvas-replacement-task__generate" disabled={!confirmed || !readyCount || isBusy} onClick={() => void submitReplacementTasks(id)}>
            <Send /> 提交 {readyCount} 个独立镜头任务
          </button>
          {hasRefreshableTasks ? <button type="button" className="canvas-replacement-task__refresh" disabled={isBusy} onClick={() => void refreshReplacementTasks(id)}>
            <RefreshCw /> 刷新 {activeCount} 个任务
          </button> : null}
          {canCompose ? <button type="button" className="canvas-replacement-task__refresh" disabled={isBusy} title="按分镜原顺序合成，未替换镜头保留原画面，并附回原声音频" onClick={() => void composeReplacementTask(id)}>
            <Layers3 /> 合成成片
          </button> : null}
        </div>
        {node.operation?.error ? <p className="canvas-replacement-task__error" role="alert">{node.operation.error}</p> : null}
        {node.operation?.status === "succeeded" && node.operation.message ? <p className="canvas-replacement-task__success"><CheckCircle2 /> {node.operation.message}</p> : null}
      </section>
    </CanvasNodeShell>
  );
}
