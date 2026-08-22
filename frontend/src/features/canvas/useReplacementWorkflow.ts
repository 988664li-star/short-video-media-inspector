import { useCallback, useState, type Dispatch, type SetStateAction } from "react";

import {
  analyzeCanvasReplaceables,
  buildCanvasReplacementPrompts,
  composeCanvasReplacementResults,
  refreshCanvasReplacementTask,
  submitCanvasReplacementTasks,
} from "../../api/canvasProjects";
import type {
  CanvasNode,
  CanvasNodeOperation,
  CanvasReplaceableObject,
  CanvasReplacementResult,
  CanvasReplacementSubject,
  CanvasReplacementTask,
  CanvasShotReplacementVersion,
  CanvasVideoModel,
} from "../../types/canvas";
import {
  createEdgeId,
  initialOperation,
  toFlowEdge,
  toFlowNode,
} from "./canvasDocument";
import type { CanvasFlowEdge, CanvasFlowNode } from "./nodes/flowTypes";
import { createCanvasNodeId } from "./nodes/nodeId";
import {
  replaceableKindLabel,
  effectiveReplacementShot,
  isRefreshableReplacementVersion,
  replacementTaskName,
  replacementPromptStatus,
  replacementVersionStatus,
  sameReplacementVersion,
  toReplacementResult,
  toShotReplacementVersion,
} from "./replacementHelpers";

function subjectFromObject(object: CanvasReplaceableObject): CanvasReplacementSubject {
  return {
    source_object_id: object.id,
    source_object_kind: object.kind,
    source_object_name: object.name,
    source_object_description: object.description,
    shot_indices: object.shot_indices,
    actions: object.actions,
    target_description: "",
  };
}

function combinedShotIndices(subjects: CanvasReplacementSubject[]) {
  return [...new Set(subjects.flatMap((subject) => subject.shot_indices))]
    .sort((left, right) => left - right);
}

function createSubjectImageNode(
  taskNode: CanvasFlowNode,
  subject: CanvasReplacementSubject,
  subjectIndex: number,
) {
  return toFlowNode({
    id: createCanvasNodeId(),
    kind: "image",
    x: taskNode.position.x - 360,
    y: taskNode.position.y + 80 + subjectIndex * 120,
    title: `目标${replaceableKindLabel(subject.source_object_kind)} · ${subject.source_object_name}`,
    detail: `仅绑定“${subject.source_object_name}”；上传参考图或输入提示词生成`,
    content: "",
    operation: initialOperation("image"),
  });
}

function subjectTargetBindings(task: CanvasReplacementTask, nodes: CanvasFlowNode[]) {
  return task.subjects.map((subject) => {
    const targetNode = subject.target_node_id
      ? nodes.find((node) => node.id === subject.target_node_id)?.data.node
      : undefined;
    return { subject, targetNode };
  });
}

interface Options {
  projectId: string;
  nodes: CanvasFlowNode[];
  setNodes: Dispatch<SetStateAction<CanvasFlowNode[]>>;
  setEdges: Dispatch<SetStateAction<CanvasFlowEdge[]>>;
  flowInstance: { fitView: (options: { nodes: Array<{ id: string }>; padding: number; duration: number }) => Promise<boolean> } | null;
  markDirty: () => void;
  updateOperation: (nodeId: string, patch: Partial<CanvasNodeOperation>) => void;
  getUpstreamNodes: (nodeId: string) => CanvasNode[];
  videoModels: CanvasVideoModel[];
}

export function useReplacementWorkflow({
  projectId, nodes, setNodes, setEdges, flowInstance, markDirty, updateOperation, getUpstreamNodes, videoModels,
}: Options) {
  const [replacementAnalysisNodeId, setReplacementAnalysisNodeId] = useState<string | null>(null);

  const analyzeReplaceables = useCallback(async (nodeId: string) => {
    const source = nodes.find((node) => node.id === nodeId);
    const shots = (source?.data.node.shot_assets ?? []).map(effectiveReplacementShot);
    if (!source || source.data.node.kind !== "shot_collection" || !shots.length) {
      updateOperation(nodeId, { status: "failed", error: "请先创建视频编辑片段，得到至少一个连续片段" });
      return;
    }
    if (replacementAnalysisNodeId) return;
    setReplacementAnalysisNodeId(nodeId);
    updateOperation(nodeId, { status: "running", error: "", message: "正在读取连续片段分镜图并识别主要替换主体…" });
    try {
      const connectedTextContexts = [...new Set(
        getUpstreamNodes(nodeId)
          .filter((node) => node.kind === "text")
          .map((node) => node.content.trim())
          .filter(Boolean),
      )];
      const sourceContext = (
        connectedTextContexts.length
          ? connectedTextContexts.join("\n\n")
          : source.data.node.source_context || source.data.node.content
      ).slice(0, 4_000);
      const result = await analyzeCanvasReplaceables(projectId, shots, sourceContext);
      const existingOutputIds = new Set(nodes
        .filter((node) => node.data.node.kind === "replaceable_analysis" && node.data.node.source_node_id === nodeId)
        .map((node) => node.id));
      const analysisNode = toFlowNode({
        id: createCanvasNodeId(),
        kind: "replaceable_analysis",
        x: source.position.x + 510,
        y: source.position.y - 12,
        title: `主要替换主体 · ${result.objects.length} 项`,
        detail: connectedTextContexts.length
          ? `已结合 ${connectedTextContexts.length} 个上游文本节点与 ${result.keyframes.length} 张连续片段分镜图完成主要主体识别`
          : `已结合来源标题文案与 ${result.keyframes.length} 张连续片段分镜图完成主要主体识别`,
        content: sourceContext,
        source_context: sourceContext,
        source_node_id: nodeId,
        analysis_keyframes: result.keyframes.map((frame) => ({
          shot_index: frame.shot_index,
          asset_id: frame.asset.id,
          asset_url: frame.asset.url,
          asset_name: frame.asset.filename,
        })),
        replaceable_objects: result.objects,
        operation: initialOperation("replaceable_analysis"),
      });
      const edge = toFlowEdge({
        id: createEdgeId({ source: nodeId, target: analysisNode.id, sourceHandle: "output", targetHandle: "input" }),
        source: nodeId,
        target: analysisNode.id,
        sourceHandle: "output",
        targetHandle: "input",
      });
      markDirty();
      setNodes((current) => [
        ...current
          .filter((node) => !existingOutputIds.has(node.id))
          .map((node) => node.id === nodeId ? {
            ...node,
            data: { node: {
              ...node.data.node,
              detail: `已识别 ${result.objects.length} 个主要替换主体；选择对象后可创建视频主体替换任务`,
              operation: {
                ...(node.data.node.operation ?? initialOperation("shot_collection")),
                status: "succeeded" as const,
                error: "",
                message: `已识别 ${result.objects.length} 个主要替换主体`,
              },
            } },
          } : node),
        { ...analysisNode, selected: true },
      ]);
      setEdges((current) => [
        ...current.filter((edge) => !existingOutputIds.has(edge.source) && !existingOutputIds.has(edge.target)),
        edge,
      ]);
    } catch (error) {
      updateOperation(nodeId, {
        status: "failed",
        error: error instanceof Error ? error.message : "可替换对象识别失败",
      });
    } finally {
      setReplacementAnalysisNodeId(null);
    }
  }, [getUpstreamNodes, nodes, projectId, replacementAnalysisNodeId, setEdges, setNodes, updateOperation]);

  const createReplacementTask = useCallback((analysisNodeId: string, objectId: string) => {
    const analysisFlowNode = nodes.find((node) => node.id === analysisNodeId);
    const analysis = analysisFlowNode?.data.node;
    const sourceNodeId = analysis?.source_node_id;
    const sourceGroup = nodes.find((node) => node.id === sourceNodeId)?.data.node;
    const sourceObject = analysis?.replaceable_objects?.find((item) => item.id === objectId);
    if (!analysisFlowNode || !analysis || !sourceNodeId || !sourceGroup || !sourceObject) return;

    const existing = nodes.find((node) => node.data.node.kind === "replacement_task"
      && node.data.node.replacement_task?.shot_collection_node_id === sourceNodeId
      && node.data.node.replacement_task?.analysis_node_id === analysisNodeId);
    if (existing) {
      const existingTask = existing.data.node.replacement_task!;
      const existingSubject = existingTask.subjects.find((subject) => subject.source_object_id === objectId);
      if (existingSubject?.target_node_id && nodes.some((node) => node.id === existingSubject.target_node_id)) {
        setNodes((current) => current.map((node) => ({
          ...node,
          selected: node.id === existingSubject.target_node_id,
        })));
        return;
      }
      const subject = existingSubject ?? subjectFromObject(sourceObject);
      const imageNode = createSubjectImageNode(existing, subject, existingTask.subjects.length);
      const subjects = existingSubject
        ? existingTask.subjects.map((item) => item.source_object_id === objectId
            ? { ...item, target_node_id: imageNode.id }
            : item)
        : [...existingTask.subjects, { ...subject, target_node_id: imageNode.id }];
      const shotIndices = combinedShotIndices(subjects);
      const primarySubject = subjects[0];
      const taskName = subjects.map((item) => item.source_object_name).join(" + ");
      markDirty();
      setNodes((current) => [
        ...current.map((node) => node.id === existing.id ? {
          ...node,
          selected: false,
          data: { node: {
            ...node.data.node,
            title: `视频主体替换 · ${taskName}`,
            detail: `一次替换 ${subjects.length} 个主体，覆盖 ${shotIndices.length} 个连续片段`,
            replacement_task: {
              ...existingTask,
              analysis_node_id: analysisNodeId,
              source_object_id: primarySubject.source_object_id,
              source_object_kind: primarySubject.source_object_kind,
              source_object_name: primarySubject.source_object_name,
              source_object_description: primarySubject.source_object_description,
              shot_indices: shotIndices,
              actions: subjects.flatMap((item) => item.actions),
              target_description: primarySubject.target_description,
              subjects,
              selected_shot_indices: [...new Set([
                ...existingTask.selected_shot_indices,
                ...subject.shot_indices,
              ])].sort((left, right) => left - right),
              shot_prompts: shotIndices.map((shotIndex) => ({
                shot_index: shotIndex,
                prompt: "",
                input_revision: 0,
                status: "pending" as const,
              })),
            },
            operation: initialOperation("replacement_task"),
          } },
        } : { ...node, selected: false }),
        { ...imageNode, selected: true },
      ]);
      const imageEdge = toFlowEdge({
        id: createEdgeId({ source: imageNode.id, target: existing.id, sourceHandle: "output", targetHandle: "input" }),
        source: imageNode.id,
        target: existing.id,
        sourceHandle: "output",
        targetHandle: "input",
      });
      setEdges((current) => [...current, imageEdge]);
      return;
    }

    const baseSubject = subjectFromObject(sourceObject);
    const taskNodeId = createCanvasNodeId();
    const taskShell = toFlowNode({
      id: taskNodeId,
      kind: "replacement_task",
      x: analysisFlowNode.position.x + 500,
      y: analysisFlowNode.position.y + 8,
      title: `视频主体替换 · ${sourceObject.name}`,
      detail: `一次替换 1 个主体，覆盖 ${sourceObject.shot_indices.length} 个连续片段`,
      content: "",
      operation: { ...initialOperation("replacement_task"), model: videoModels[0]?.id ?? "" },
    });
    const imageNode = createSubjectImageNode(taskShell, baseSubject, 0);
    const subject = { ...baseSubject, target_node_id: imageNode.id };
    const task: CanvasReplacementTask = {
      analysis_node_id: analysisNodeId,
      shot_collection_node_id: sourceNodeId,
      source_object_id: sourceObject.id,
      source_object_kind: sourceObject.kind,
      source_object_name: sourceObject.name,
      source_object_description: sourceObject.description,
      shot_indices: sourceObject.shot_indices,
      actions: sourceObject.actions,
      target_description: "",
      subjects: [subject],
      selected_shot_indices: sourceObject.shot_indices,
      shot_prompts: sourceObject.shot_indices.map((shotIndex) => ({ shot_index: shotIndex, prompt: "", input_revision: 0, status: "pending" })),
    };
    const taskNode = toFlowNode({
      id: taskNodeId,
      kind: "replacement_task",
      x: analysisFlowNode.position.x + 500,
      y: analysisFlowNode.position.y + 8,
      title: `视频主体替换 · ${sourceObject.name}`,
      detail: `一次替换 1 个主体，覆盖 ${sourceObject.shot_indices.length} 个连续片段`,
      content: "",
      replacement_task: task,
      operation: { ...initialOperation("replacement_task"), model: videoModels[0]?.id ?? "" },
    });
    const connections = [sourceNodeId, analysisNodeId, imageNode.id].map((source) => toFlowEdge({
      id: createEdgeId({ source, target: taskNode.id, sourceHandle: "output", targetHandle: "input" }),
      source,
      target: taskNode.id,
      sourceHandle: "output",
      targetHandle: "input",
    }));
    markDirty();
    setNodes((current) => [
      ...current.map((node) => ({ ...node, selected: false })),
      { ...taskNode, selected: false },
      { ...imageNode, selected: true },
    ]);
    setEdges((current) => [...current, ...connections]);
  }, [nodes, setEdges, setNodes, videoModels]);

  const updateReplacementTask = useCallback((nodeId: string, patch: Partial<CanvasReplacementTask>) => {
    markDirty();
    setNodes((current) => current.map((node) => node.id === nodeId && node.data.node.replacement_task ? {
      ...node,
      data: { node: {
        ...node.data.node,
        replacement_task: { ...node.data.node.replacement_task, ...patch },
        operation: { ...(node.data.node.operation ?? initialOperation("replacement_task")), status: "idle", error: "", message: "" },
      } },
    } : node));
  }, [setNodes]);

  const toggleReplacementShot = useCallback((nodeId: string, shotIndex: number) => {
    const task = nodes.find((node) => node.id === nodeId)?.data.node.replacement_task;
    if (!task) return;
    const selected = task.selected_shot_indices.includes(shotIndex)
      ? task.selected_shot_indices.filter((index) => index !== shotIndex)
      : [...task.selected_shot_indices, shotIndex].sort((left, right) => left - right);
    updateReplacementTask(nodeId, {
      selected_shot_indices: selected,
    });
  }, [nodes, updateReplacementTask]);

  const updateReplacementShotPrompt = useCallback((nodeId: string, shotIndex: number, prompt: string) => {
    const task = nodes.find((node) => node.id === nodeId)?.data.node.replacement_task;
    if (!task) return;
    updateReplacementTask(nodeId, {
      shot_prompts: task.shot_prompts.map((item) => item.shot_index === shotIndex
        ? { ...item, prompt, status: prompt.trim() ? "ready" : "pending" }
        : item),
    });
  }, [nodes, updateReplacementTask]);

  const buildReplacementPrompts = useCallback(async (nodeId: string) => {
    const flowNode = nodes.find((node) => node.id === nodeId);
    const task = flowNode?.data.node.replacement_task;
    if (!flowNode || !task) return;
    const bindings = subjectTargetBindings(task, nodes);
    const missingSubjects = bindings
      .filter(({ targetNode }) => targetNode?.kind !== "image" || !targetNode.asset_id)
      .map(({ subject }) => subject.source_object_name);
    const targetAssetIds = bindings.map(({ targetNode }) => targetNode?.asset_id).filter(Boolean) as string[];
    const sourceGroup = nodes.find((node) => node.id === task.shot_collection_node_id)?.data.node;
    const selectedShots = (sourceGroup?.shot_assets ?? [])
      .map(effectiveReplacementShot)
      .filter((shot) => task.selected_shot_indices.includes(shot.index));
    if (missingSubjects.length) {
      updateOperation(nodeId, {
        status: "failed",
        error: `请先为“${missingSubjects.join("、")}”上传各自的目标参考图`,
      });
      return;
    }
    if (!selectedShots.length) {
      updateOperation(nodeId, { status: "failed", error: "请至少勾选一个需要替换的镜头" });
      return;
    }
    updateOperation(nodeId, { status: "running", error: "", message: "正在按所选镜头生成视频编辑指令…" });
    try {
      const result = await buildCanvasReplacementPrompts(projectId, {
        source_object_name: task.source_object_name,
        source_object_description: task.source_object_description,
        target_description: task.target_description,
        target_asset_ids: targetAssetIds,
        shots: selectedShots,
        actions: task.actions,
        subjects: bindings.map(({ subject, targetNode }) => ({
          source_object_id: subject.source_object_id,
          source_object_kind: subject.source_object_kind,
          source_object_name: subject.source_object_name,
          source_object_description: subject.source_object_description,
          shot_indices: subject.shot_indices,
          actions: subject.actions,
          target_description: subject.target_description,
          target_asset_ids: [targetNode!.asset_id!],
        })),
      });
      const promptByShot = new Map(
        result.prompts
          .filter((prompt) => prompt.prompt.trim())
          .map((prompt) => [prompt.shot_index, prompt]),
      );
      const missingShotIndices = selectedShots
        .filter((shot) => !promptByShot.has(shot.index))
        .map((shot) => String(shot.index).padStart(2, "0"));
      if (missingShotIndices.length) {
        throw new Error(`镜头 ${missingShotIndices.join("、")} 的提示词为空，未保存；请重新生成`);
      }
      updateReplacementTask(nodeId, {
        shot_prompts: task.shot_prompts.map((item) => task.selected_shot_indices.includes(item.shot_index)
          ? promptByShot.get(item.shot_index)!
          : item),
      });
      updateOperation(nodeId, { status: "succeeded", error: "", message: `已生成 ${result.prompts.length} 条可审查的视频编辑指令` });
    } catch (error) {
      updateOperation(nodeId, { status: "failed", error: error instanceof Error ? error.message : "逐镜头提示词生成失败" });
    }
  }, [nodes, projectId, updateOperation, updateReplacementTask]);

  const submitReplacementTasks = useCallback(async (nodeId: string, onlyShotIndex?: number) => {
    const flowNode = nodes.find((node) => node.id === nodeId);
    const task = flowNode?.data.node.replacement_task;
    if (!flowNode || !task) return;
    const bindings = subjectTargetBindings(task, nodes);
    const missingSubjects = bindings
      .filter(({ targetNode }) => targetNode?.kind !== "image" || !targetNode.asset_id)
      .map(({ subject }) => subject.source_object_name);
    if (missingSubjects.length) {
      updateOperation(nodeId, {
        status: "failed",
        error: `请先为“${missingSubjects.join("、")}”上传各自的目标参考图`,
      });
      return;
    }
    const targetAssetIds = bindings.map(({ targetNode }) => targetNode!.asset_id!);
    const sourceGroup = nodes.find((node) => node.id === task.shot_collection_node_id)?.data.node;
    const outputGroup = task.output_shot_collection_node_id
      ? nodes.find((node) => node.id === task.output_shot_collection_node_id)?.data.node
      : undefined;
    const existingVersionByShot = new Map((outputGroup?.shot_assets ?? []).map((shot) => [
      shot.index,
      shot.replacement_versions?.find((version) => version.task_node_id === nodeId),
    ]));
    const selectedShots = (sourceGroup?.shot_assets ?? []).map(effectiveReplacementShot).filter((shot) => onlyShotIndex
      ? shot.index === onlyShotIndex
      : task.selected_shot_indices.includes(shot.index)).filter((shot) => {
      if (onlyShotIndex) return true;
      const existing = existingVersionByShot.get(shot.index);
      return !existing || existing.status === "failed";
    });
    if (!selectedShots.length) {
      updateOperation(nodeId, { status: "failed", error: "已选镜头均已提交；如需重做，请展开该镜头的提示词后单独重新生成。" });
      return;
    }
    const existingSingleVersion = onlyShotIndex ? existingVersionByShot.get(onlyShotIndex) : undefined;
    if (existingSingleVersion?.status === "pending"
      || existingSingleVersion?.status === "queued"
      || existingSingleVersion?.status === "running") {
      updateOperation(nodeId, { status: "failed", error: "当前片段仍在生成中，请完成后再重新生成。" });
      return;
    }
    const prompts = task.shot_prompts.filter((prompt) => {
      const isSelected = onlyShotIndex
        ? prompt.shot_index === onlyShotIndex
        : task.selected_shot_indices.includes(prompt.shot_index);
      return isSelected && (onlyShotIndex ? Boolean(prompt.prompt.trim()) : prompt.status === "ready");
    });
    const selectedModel = flowNode.data.node.operation?.model || videoModels[0]?.id;
    const selectedModelProfile = videoModels.find((model) => model.id === selectedModel);
    if (!selectedModel || !selectedModelProfile) {
      updateOperation(nodeId, { status: "failed", error: "当前没有可用的视频编辑模型" });
      return;
    }
    const outOfRangeShots = selectedShots.filter((shot) => (
      shot.duration_seconds < selectedModelProfile.min_duration_seconds
      || shot.duration_seconds > selectedModelProfile.max_duration_seconds
    ));
    if (outOfRangeShots.length) {
      updateOperation(nodeId, {
        status: "failed",
        error: `片段 ${outOfRangeShots.map((shot) => String(shot.index).padStart(2, "0")).join("、")} 不在当前模型 ${selectedModelProfile.min_duration_seconds}–${selectedModelProfile.max_duration_seconds} 秒范围内。请在原视频节点重新执行“创建编辑片段”。`,
      });
      return;
    }
    if (prompts.length !== selectedShots.length) {
      updateOperation(nodeId, { status: "failed", error: "请先为所有已选镜头生成并审核视频指令" });
      return;
    }
    if (prompts.some((prompt) => prompt.input_revision !== 3)) {
      updateOperation(nodeId, { status: "failed", error: "视频编辑指令使用的是旧结构。请点击“生成视频编辑指令”重新构建后再提交。" });
      return;
    }
    updateOperation(nodeId, { status: "running", error: "", message: `正在提交 ${selectedShots.length} 个完整视频编辑任务…` });
    try {
      const requestedOutputGroupId = task.output_shot_collection_node_id || createCanvasNodeId();
      const response = await submitCanvasReplacementTasks(projectId, {
        task_node_id: nodeId,
        output_shot_collection_node_id: requestedOutputGroupId,
        model: selectedModel,
        target_asset_ids: targetAssetIds,
        shots: selectedShots,
        prompts,
        confirmed: true,
      });
      const results = response.results.map(toReplacementResult);
      const resultByShot = new Map(results.map((result) => [result.shot_index, result]));
      const outputGroupId = response.output_shot_collection_node_id;
      const outputGroupNode = task.output_shot_collection_node_id ? null : toFlowNode({
        id: outputGroupId,
        kind: "shot_collection",
        x: flowNode.position.x + 590,
        y: flowNode.position.y + 12,
        title: `替换镜头组 · ${replacementTaskName(task)}`,
        detail: `已提交 ${results.length} 个镜头任务；节点会自动刷新生成结果`,
        content: "",
        source_node_id: nodeId,
        shot_assets: selectedShots.map((shot) => ({
          ...shot,
          replacement_versions: [toShotReplacementVersion(nodeId, task, resultByShot.get(shot.index)!)],
        })),
        operation: initialOperation("shot_collection"),
      });
      const outputEdge = toFlowEdge({
        id: createEdgeId({ source: nodeId, target: outputGroupId, sourceHandle: "output", targetHandle: "input" }),
        source: nodeId,
        target: outputGroupId,
        sourceHandle: "output",
        targetHandle: "input",
      });
      markDirty();
      setNodes((current) => {
        const updated = current.map((node) => {
          if (node.id === outputGroupId) {
            return {
              ...node,
              data: { node: {
                ...node.data.node,
                detail: `已提交 ${results.length} 个镜头任务；正在自动刷新生成结果`,
                shot_assets: [
                  ...(node.data.node.shot_assets ?? []).map((shot) => {
                    const result = resultByShot.get(shot.index);
                    if (!result) return shot;
                    const version = toShotReplacementVersion(nodeId, task, result);
                    return {
                      ...shot,
                      replacement_versions: [
                        ...(shot.replacement_versions ?? []).filter((item) => item.task_node_id !== nodeId),
                        version,
                      ],
                    };
                  }),
                  ...selectedShots
                    .filter((shot) => !(node.data.node.shot_assets ?? []).some((item) => item.index === shot.index))
                    .map((shot) => ({
                      ...shot,
                      replacement_versions: [toShotReplacementVersion(nodeId, task, resultByShot.get(shot.index)!)],
                    })),
                ].sort((left, right) => left.index - right.index),
              } },
              selected: true,
            };
          }
          if (node.id === nodeId && node.data.node.replacement_task) {
            return {
              ...node,
              data: { node: {
                ...node.data.node,
                detail: `已提交 ${results.length} 个独立镜头任务；结果会自动回写到替换镜头组`,
                replacement_task: {
                  ...node.data.node.replacement_task,
                  output_shot_collection_node_id: outputGroupId,
                  shot_prompts: node.data.node.replacement_task.shot_prompts.map((prompt) => {
                    const result = resultByShot.get(prompt.shot_index);
                    return result ? {
                      ...prompt,
                      status: replacementPromptStatus(result.status),
                      provider_task_id: result.provider_task_id,
                      result_asset_id: result.result_asset_id,
                      error: result.error,
                    } : prompt;
                  }),
                },
                operation: { ...(node.data.node.operation ?? initialOperation("replacement_task")), status: "succeeded" as const, error: "", message: `已提交 ${results.length} 个独立镜头任务，正在自动刷新结果` },
              } },
              selected: false,
            };
          }
          return { ...node, selected: false };
        });
        return outputGroupNode ? [...updated, { ...outputGroupNode, selected: true }] : updated;
      });
      setEdges((current) => current.some((edge) => edge.id === outputEdge.id) ? current : [...current, outputEdge]);
      window.requestAnimationFrame(() => {
        void flowInstance?.fitView({ nodes: [{ id: outputGroupId }], padding: 0.5, duration: 220 });
      });
    } catch (error) {
      updateOperation(nodeId, { status: "failed", error: error instanceof Error ? error.message : "逐镜头视频替换提交失败" });
    }
  }, [flowInstance, nodes, projectId, setEdges, setNodes, toReplacementResult, toShotReplacementVersion, updateOperation, videoModels]);

  const refreshReplacementOutputGroup = useCallback(async (outputGroupId: string) => {
    const outputGroup = nodes.find((node) => node.id === outputGroupId)?.data.node;
    if (!outputGroup || outputGroup.kind !== "shot_collection") return;
    const refreshable = (outputGroup.shot_assets ?? []).flatMap((shot) => (
      (shot.replacement_versions ?? [])
        .filter(isRefreshableReplacementVersion)
        .map((version) => ({ shot, version }))
    ));
    if (!refreshable.length) return;
    const settled = await Promise.allSettled(refreshable.map(async ({ shot, version }) => {
      const response = await refreshCanvasReplacementTask(projectId, {
        model: version.model,
        provider_task_id: version.provider_task_id,
        task_node_id: version.task_node_id,
        output_shot_collection_node_id: outputGroupId,
        shot,
        result_asset_id: version.result_asset_id,
      });
      return { shotIndex: shot.index, taskNodeId: version.task_node_id, result: toReplacementResult(response.result) };
    }));
    const updates = new Map<string, CanvasShotReplacementVersion>();
    settled.forEach((item, index) => {
      const { shot, version } = refreshable[index];
      const key = `${shot.index}:${version.task_node_id}`;
      if (item.status === "fulfilled") {
        updates.set(key, {
          ...version,
          provider_task_id: item.value.result.provider_task_id,
          status: replacementVersionStatus(item.value.result.status),
          result_asset_id: item.value.result.result_asset_id,
          result_asset_url: item.value.result.result_asset_url,
          result_asset_name: item.value.result.result_asset_name,
          error: item.value.result.error,
        });
      } else {
        const refreshError = item.reason instanceof Error ? item.reason.message : "任务刷新失败";
        updates.set(key, {
          ...version,
          status: version.status === "failed" ? "queued" : version.status,
          error: `状态刷新暂时失败：${refreshError}`,
        });
      }
    });
    const hasChanges = [...updates.entries()].some(([key, nextVersion]) => {
      const [shotIndex, taskNodeId] = key.split(":");
      const currentVersion = (outputGroup.shot_assets ?? [])
        .find((shot) => shot.index === Number(shotIndex))?.replacement_versions
        ?.find((version) => version.task_node_id === taskNodeId);
      return !currentVersion || !sameReplacementVersion(currentVersion, nextVersion);
    });
    if (!hasChanges) return;
    markDirty();
    setNodes((current) => current.map((node) => {
      if (node.id !== outputGroupId) return node;
      return {
        ...node,
        data: { node: {
          ...node.data.node,
          shot_assets: (node.data.node.shot_assets ?? []).map((shot) => ({
            ...shot,
            replacement_versions: (shot.replacement_versions ?? []).map((version) => (
              updates.get(`${shot.index}:${version.task_node_id}`) ?? version
            )),
          })),
        } },
      };
    }));
  }, [nodes, projectId, setNodes, toReplacementResult]);

  const composeReplacementOutputGroup = useCallback(async (outputGroupId: string) => {
    const outputShotGroup = nodes.find((node) => node.id === outputGroupId);
    const taskNodeId = outputShotGroup?.data.node.source_node_id;
    const taskNode = nodes.find((node) => node.id === taskNodeId);
    const task = taskNode?.data.node.replacement_task;
    const sourceShotGroup = nodes.find((node) => node.id === task?.shot_collection_node_id);
    const connectedAudioNodes = getUpstreamNodes(outputGroupId).filter((node) => (
      (node.kind === "audio" || node.kind === "music") && node.asset_id
    ));
    if (connectedAudioNodes.length > 1) {
      updateOperation(outputGroupId, {
        status: "failed",
        error: "结果组连接了多条音频，请只保留一条需要加入成片的音频连接",
      });
      return;
    }
    const shots = sourceShotGroup?.data.node.shot_assets ?? [];
    const results = (outputShotGroup?.data.node.shot_assets ?? []).flatMap((shot): CanvasReplacementResult[] => {
      const version = shot.replacement_versions?.find((item) => item.task_node_id === taskNodeId);
      return version ? [{
        shot_index: shot.index,
        source_asset_id: shot.asset_id,
        source_asset_name: shot.asset_name,
        duration_seconds: shot.duration_seconds,
        model: version.model,
        provider_task_id: version.provider_task_id,
        status: version.status,
        result_asset_id: version.result_asset_id,
        result_asset_url: version.result_asset_url,
        result_asset_name: version.result_asset_name,
        error: version.error,
      }] : [];
    });
    if (!outputShotGroup || !taskNode || !shots.length || !results.length) {
      updateOperation(outputGroupId, { status: "failed", error: "缺少原始镜头组或替换结果，暂时不能合成" });
      return;
    }
    const connectedAudio = connectedAudioNodes[0];
    updateOperation(outputGroupId, {
      status: "running",
      error: "",
      message: connectedAudio ? "正在合并镜头并加入已连接音频…" : "正在合并无声成片…",
    });
    try {
      const response = await composeCanvasReplacementResults(projectId, {
        shots,
        results,
        source_audio_asset_id: connectedAudio?.asset_id,
      });
      const outputNode = toFlowNode({
        id: createCanvasNodeId(),
        kind: "video",
        x: outputShotGroup.position.x + 520,
        y: outputShotGroup.position.y + 32,
        title: "主体替换完整成片",
        detail: response.used_original_shot_indices.length
          ? `已合成；镜头 ${response.used_original_shot_indices.map((index) => String(index).padStart(2, "0")).join("、")} 保留原画面`
          : connectedAudio ? `已合成全部替换镜头，并加入音频“${connectedAudio.title}”` : "已合成全部替换镜头，无音频",
        content: "",
        asset_id: response.asset.id,
        asset_url: response.asset.url,
        asset_name: response.asset.filename,
        source_node_id: outputGroupId,
        operation: initialOperation("video"),
      });
      const outputEdge = toFlowEdge({
        id: createEdgeId({ source: outputGroupId, target: outputNode.id, sourceHandle: "output", targetHandle: "input" }),
        source: outputGroupId,
        target: outputNode.id,
        sourceHandle: "output",
        targetHandle: "input",
      });
      markDirty();
      setNodes((current) => [
        ...current.map((node) => node.id === outputGroupId ? {
          ...node,
          data: { node: {
            ...node.data.node,
            detail: `已合成替换成片${response.used_original_shot_indices.length ? "，失败或未选镜头保留原画面" : ""}`,
            operation: { ...(node.data.node.operation ?? initialOperation("shot_collection")), status: "succeeded" as const, error: "", message: connectedAudio ? "含音频成片已生成并保存" : "无声成片已生成并保存" },
          } },
        } : node),
        { ...outputNode, selected: true },
      ]);
      setEdges((current) => [...current, outputEdge]);
    } catch (error) {
      updateOperation(outputGroupId, { status: "failed", error: error instanceof Error ? error.message : "逐镜头替换成片合成失败" });
    }
  }, [getUpstreamNodes, nodes, projectId, setEdges, setNodes, updateOperation]);

  const addTargetImageNode = useCallback((replacementTaskNodeId: string, sourceObjectId: string) => {
    const taskNode = nodes.find((node) => node.id === replacementTaskNodeId);
    const task = taskNode?.data.node.replacement_task;
    const subjectIndex = task?.subjects.findIndex((item) => item.source_object_id === sourceObjectId) ?? -1;
    if (!taskNode || !task || subjectIndex < 0) return;
    const subject = task.subjects[subjectIndex];
    if (subject.target_node_id && nodes.some((node) => node.id === subject.target_node_id)) {
      setNodes((current) => current.map((node) => ({
        ...node,
        selected: node.id === subject.target_node_id,
      })));
      return;
    }
    const imageNode = createSubjectImageNode(taskNode, subject, subjectIndex);
    const edge = toFlowEdge({
      id: createEdgeId({ source: imageNode.id, target: replacementTaskNodeId, sourceHandle: "output", targetHandle: "input" }),
      source: imageNode.id,
      target: replacementTaskNodeId,
      sourceHandle: "output",
      targetHandle: "input",
    });
    markDirty();
    setNodes((current) => [
      ...current.map((node) => node.id === replacementTaskNodeId && node.data.node.replacement_task ? {
        ...node,
        selected: false,
        data: { node: {
          ...node.data.node,
          replacement_task: {
            ...node.data.node.replacement_task,
            subjects: node.data.node.replacement_task.subjects.map((item) => (
              item.source_object_id === sourceObjectId
                ? { ...item, target_node_id: imageNode.id }
                : item
            )),
          },
        } },
      } : { ...node, selected: false }),
      { ...imageNode, selected: true },
    ]);
    setEdges((current) => [...current, edge]);
  }, [nodes, setEdges, setNodes]);


  return {
    replacementAnalysisNodeId,
    analyzeReplaceables,
    createReplacementTask,
    updateReplacementTask,
    toggleReplacementShot,
    updateReplacementShotPrompt,
    buildReplacementPrompts,
    submitReplacementTasks,
    refreshReplacementOutputGroup,
    composeReplacementOutputGroup,
    addTargetImageNode,
  };
}
