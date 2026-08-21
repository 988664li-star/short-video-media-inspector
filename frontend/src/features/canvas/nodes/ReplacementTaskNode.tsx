import { ChevronDown, ChevronUp, Image as ImageIcon, Link2, WandSparkles } from "lucide-react";
import type { NodeProps } from "@xyflow/react";
import { useMemo, useState } from "react";

import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeShell } from "./CanvasNodeShell";
import type { CanvasFlowNode } from "./flowTypes";

function kindLabel(kind: string) {
  return { product: "商品", person: "人物", background: "背景", text: "文字", other: "对象" }[kind] || "对象";
}

export function ReplacementTaskNode({ id, data, selected }: NodeProps<CanvasFlowNode>) {
  const {
    buildReplacementPrompts,
    getUpstreamNodes,
    previewMedia,
    updateReplacementShotPrompt,
    updateReplacementTask,
  } = useCanvasNodeActions();
  const { node } = data;
  const task = node.replacement_task;
  const [showAll, setShowAll] = useState(false);
  const targetImages = useMemo(() => getUpstreamNodes(id)
    .filter((upstream) => upstream.kind === "image" && upstream.asset_id && upstream.asset_url), [getUpstreamNodes, id]);

  if (!task) return null;
  const prompts = showAll ? task.shot_prompts : task.shot_prompts.slice(0, 3);
  const readyCount = task.shot_prompts.filter((item) => item.status === "ready" || item.status === "generated").length;

  return (
    <CanvasNodeShell node={node} selected={selected} label="镜头替换任务" icon={<WandSparkles />}>
      <section className="canvas-replacement-task nodrag nowheel">
        <header className="canvas-replacement-task__summary">
          <div><span>{kindLabel(task.source_object_kind)}替换</span><strong>{task.source_object_name}</strong></div>
          <p>覆盖 {task.shot_indices.length} 个镜头 · 已就绪 {readyCount}</p>
        </header>

        <div className="canvas-replacement-task__materials">
          <span><Link2 /> 目标素材</span>
          {targetImages.length ? <div>
            {targetImages.map((image) => <button key={image.id} type="button" title={`预览：${image.asset_name || image.title}`} onClick={() => previewMedia(image)}>
              <img src={image.asset_url} alt={image.asset_name || image.title} />
            </button>)}
          </div> : <p>连接一个或多个图片节点到这里</p>}
        </div>

        <label className="canvas-replacement-task__target-description">
          <span>目标{kindLabel(task.source_object_kind)}说明（可选）</span>
          <input
            value={task.target_description}
            placeholder="例如：浅色木质托盘，圆角边框，保留自然木纹"
            onKeyDown={(event) => event.stopPropagation()}
            onChange={(event) => updateReplacementTask(id, { target_description: event.target.value })}
          />
        </label>

        <button className="canvas-replacement-task__build" type="button" disabled={!targetImages.length} onClick={() => buildReplacementPrompts(id)}>
          <WandSparkles /> 生成逐镜头提示词
        </button>
        {!targetImages.length ? <p className="canvas-replacement-task__hint"><ImageIcon /> 从图片节点拖一条线到本任务；目标图会在每个镜头提示词中作为参考。</p> : null}

        <div className="canvas-replacement-task__prompts">
          <header><strong>镜头提示词</strong><span>{task.shot_prompts.length} 条</span></header>
          {prompts.map((item) => (
            <details key={item.shot_index} className="canvas-replacement-task__prompt">
              <summary>
                <span>镜头 {String(item.shot_index).padStart(2, "0")}</span>
                <small>{item.status === "ready" ? "已就绪" : "待生成"}</small>
                <ChevronDown className="canvas-replacement-task__down" />
                <ChevronUp className="canvas-replacement-task__up" />
              </summary>
              <textarea
                rows={9}
                value={item.prompt}
                placeholder="生成后可在此审核和修改本镜头提示词…"
                onKeyDown={(event) => event.stopPropagation()}
                onChange={(event) => updateReplacementShotPrompt(id, item.shot_index, event.target.value)}
              />
            </details>
          ))}
          {task.shot_prompts.length > 3 ? <button className="canvas-replacement-task__show-all" type="button" onClick={() => setShowAll((current) => !current)}>
            {showAll ? "收起其余镜头" : `查看全部 ${task.shot_prompts.length} 个镜头`}
          </button> : null}
        </div>
        {node.operation?.error ? <p className="canvas-replacement-task__error" role="alert">{node.operation.error}</p> : null}
        {node.operation?.status === "succeeded" && node.operation.message ? <p className="canvas-replacement-task__success">{node.operation.message}</p> : null}
      </section>
    </CanvasNodeShell>
  );
}
