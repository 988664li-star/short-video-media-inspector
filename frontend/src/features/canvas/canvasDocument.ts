import { MarkerType, type Connection } from "@xyflow/react";

import type {
  CanvasAsset,
  CanvasEdge,
  CanvasMediaExtractionResult,
  CanvasNode,
  CanvasNodeKind,
  CanvasNodeOperation,
  CanvasReferenceAsset,
  CanvasReplacementSubject,
  CanvasReplacementTask,
} from "../../types/canvas";
import { createCanvasNodeId } from "./nodes/nodeId";
import type { CanvasFlowEdge, CanvasFlowNode } from "./nodes/flowTypes";
import { normalizeReferenceAssets } from "./referenceAssets";

export const TEXT_MODEL = "Qwen/Qwen3.6-27B";
export const IMAGE_MODEL = "doubao-seedream-5-0-260128";

export const defaultCanvasEdgeOptions = {
  type: "canvas",
  animated: false,
  markerEnd: { type: MarkerType.ArrowClosed, color: "#66d0b1", width: 16, height: 16 },
};

export function initialOperation(kind: CanvasNodeKind): CanvasNodeOperation {
  return {
    prompt: "",
    model: kind === "image" ? IMAGE_MODEL : kind === "text" ? TEXT_MODEL : "",
    source_url: "",
    referenced_asset_ids: [],
    style: "自然",
    aspect_ratio: kind === "image" || kind === "video" ? "原比例" : "",
    quality: kind === "image" || kind === "video" ? "1K" : "",
    role_mode: "通用",
    status: "idle",
    error: "",
  };
}

export function nodeTitle(kind: CanvasNodeKind) {
  const titles: Record<CanvasNodeKind, string> = {
    text: "文本",
    image: "图片素材",
    video: "视频素材",
    shot_collection: "分镜组",
    replaceable_analysis: "可替换对象分析",
    replacement_task: "视频主体替换任务",
    extractor: "链接提取",
    music: "作品配乐",
    audio: "视频混合音频",
  };
  return titles[kind];
}

export function createCanvasNode(kind: CanvasNodeKind, position: { x: number; y: number }): CanvasNode {
  const detail = kind === "text"
    ? "输入文本内容"
    : kind === "extractor"
      ? "输入分享链接，自动生成实际返回的媒体节点"
      : kind === "image"
        ? "上传参考图，或直接输入提示词生成"
        : kind === "video"
          ? "上传视频，或直接配置视频创作指令"
          : "点击预览按钮查看素材";
  return { id: createCanvasNodeId(), kind, x: position.x, y: position.y, title: nodeTitle(kind), detail, content: "", operation: initialOperation(kind) };
}

export function extractedMediaNodes(
  result: CanvasMediaExtractionResult,
  extractorId: string,
  position: { x: number; y: number },
): CanvasNode[] {
  const { video, music, audio } = result.outputs;
  const sourceContext = result.description.trim();
  const specs: Array<{ kind: "video" | "music" | "audio"; title: string; detail: string; asset: CanvasAsset }> = [];

  if (video.available && video.asset) {
    specs.push({ kind: "video", title: "原视频", detail: result.description.slice(0, 600), asset: video.asset });
  }
  if (music.available && music.asset && audio.available && audio.asset && music.asset.id === audio.asset.id) {
    specs.push({
      kind: "audio",
      title: "视频混合音频",
      detail: "平台只返回一条音频流；其中可能同时包含人声与背景音乐。",
      asset: audio.asset,
    });
  } else {
    if (music.available && music.asset) specs.push({ kind: "music", title: "作品配乐", detail: music.message, asset: music.asset });
    if (audio.available && audio.asset) specs.push({ kind: "audio", title: "视频混合音频", detail: audio.message, asset: audio.asset });
  }

  const captionNodes: CanvasNode[] = sourceContext ? [{
    id: createCanvasNodeId(),
    kind: "text",
    x: position.x + 470,
    y: position.y - 120,
    title: "作品标题/发布文案",
    detail: "链接平台返回的作品标题或发布文案，可编辑并作为后续分析的语义参考",
    content: sourceContext,
    source_context: sourceContext.slice(0, 4_000),
    source_extractor_id: extractorId,
    operation: initialOperation("text"),
  }] : [];
  const mediaStartY = position.y - 120 + (captionNodes.length ? 260 : 0);

  const mediaNodes: CanvasNode[] = specs.map((spec, index) => ({
    id: createCanvasNodeId(),
    kind: spec.kind,
    x: position.x + 470,
    y: mediaStartY + index * 230,
    title: spec.title,
    detail: spec.detail,
    content: spec.kind === "video" ? sourceContext : "",
    source_context: sourceContext.slice(0, 4_000),
    asset_id: spec.asset.id,
    asset_url: spec.asset.url,
    asset_name: spec.asset.filename,
    source_extractor_id: extractorId,
    availability_message: spec.detail,
    operation: initialOperation(spec.kind),
  }));

  return [...captionNodes, ...mediaNodes];
}

export function normalizeMaterialReferenceOperation(node: CanvasNode) {
  const operation = node.operation ?? initialOperation(node.kind);
  const selectedAssetIds = new Set(operation.referenced_asset_ids ?? []);
  const referencedFilenames = (node.reference_assets ?? [])
    .filter((asset) => selectedAssetIds.has(asset.id))
    .map((asset) => asset.filename);
  const prompt = referencedFilenames.reduce(
    (current, filename) => current.replaceAll(`@${filename}`, ""),
    operation.prompt,
  ).replace(/[ \t]{2,}/g, " ").trimStart();
  return prompt === operation.prompt ? operation : { ...operation, prompt };
}

export function hasLegacyMaterialReferenceToken(node: CanvasNode) {
  return normalizeMaterialReferenceOperation(node).prompt !== (node.operation ?? initialOperation(node.kind)).prompt;
}

export function referenceAssetFromNode(node: CanvasNode): CanvasReferenceAsset | null {
  if (!node.asset_id || !node.asset_url || !node.asset_name) return null;
  const mimeType = node.kind === "image" ? "image/*" : node.kind === "video" ? "video/*" : "audio/*";
  return { id: node.asset_id, url: node.asset_url, filename: node.asset_name, mime_type: mimeType, label: node.title };
}

export function toFlowNode(node: CanvasNode): CanvasFlowNode {
  const legacyNode = node as CanvasNode & {
    replacement_results?: unknown;
    replacement_task?: Omit<CanvasReplacementTask, "subjects"> & {
      subjects?: CanvasReplacementSubject[];
      result_group_node_id?: unknown;
    };
  };
  const { replacement_results: _replacementResults, ...currentNode } = legacyNode;
  const legacyTask = currentNode.replacement_task;
  let replacementTask: CanvasReplacementTask | undefined;
  if (legacyTask) {
    const { result_group_node_id: _resultGroupNodeId, ...currentTask } = legacyTask;
    const subjects = Array.isArray(legacyTask.subjects) && legacyTask.subjects.length
      ? legacyTask.subjects
      : [{
          source_object_id: legacyTask.source_object_id,
          source_object_kind: legacyTask.source_object_kind,
          source_object_name: legacyTask.source_object_name,
          source_object_description: legacyTask.source_object_description,
          shot_indices: legacyTask.shot_indices,
          actions: legacyTask.actions,
          target_description: legacyTask.target_description,
        }];
    replacementTask = {
      ...currentTask,
      subjects,
      selected_shot_indices: Array.isArray(legacyTask.selected_shot_indices)
        ? legacyTask.selected_shot_indices
        : legacyTask.shot_indices,
      shot_prompts: legacyTask.shot_prompts.map((prompt) => ({
        ...prompt,
        input_revision: prompt.input_revision ?? 0,
        provider_task_id: prompt.provider_task_id ?? "",
        result_asset_id: prompt.result_asset_id ?? "",
        error: prompt.error ?? "",
      })),
    };
  }
  return {
    id: node.id,
    type: node.kind,
    position: { x: node.x, y: node.y },
    data: {
      node: {
        ...currentNode,
        source_context: currentNode.source_context ?? "",
        replacement_task: replacementTask,
        reference_assets: normalizeReferenceAssets(currentNode.reference_assets),
        operation: normalizeMaterialReferenceOperation(currentNode),
      },
    },
  };
}

export function toCanvasNode(node: CanvasFlowNode): CanvasNode {
  return { ...node.data.node, x: node.position.x, y: node.position.y };
}

export function toFlowEdge(edge: CanvasEdge): CanvasFlowEdge {
  return { ...edge, ...defaultCanvasEdgeOptions };
}

export function toCanvasEdge(edge: CanvasFlowEdge): CanvasEdge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle ?? undefined,
    targetHandle: edge.targetHandle ?? undefined,
  };
}

export function createEdgeId(connection: Connection) {
  return `edge-${connection.source}-${connection.target}-${createCanvasNodeId().replace("node-", "")}`;
}

function withoutTargetNodeId(subject: CanvasReplacementSubject): CanvasReplacementSubject {
  const { target_node_id: _targetNodeId, ...unboundSubject } = subject;
  return unboundSubject;
}

/** Keep replacement bindings from retaining an image node that no longer exists. */
export function clearDeletedReplacementTargetBindings(
  nodes: CanvasFlowNode[],
  deletedNodeIds: ReadonlySet<string>,
): CanvasFlowNode[] {
  if (!deletedNodeIds.size) return nodes;
  let changed = false;
  const nextNodes = nodes.map((node) => {
    const task = node.data.node.replacement_task;
    if (node.data.node.kind !== "replacement_task" || !task) return node;
    let taskChanged = false;
    const subjects = task.subjects.map((subject) => {
      if (!subject.target_node_id || !deletedNodeIds.has(subject.target_node_id)) return subject;
      taskChanged = true;
      changed = true;
      return withoutTargetNodeId(subject);
    });
    if (!taskChanged) return node;
    return {
      ...node,
      data: { node: {
        ...node.data.node,
        replacement_task: { ...task, subjects },
      } },
    };
  });
  return changed ? nextNodes : nodes;
}

/** Bind a manually connected image to the first subject whose target was removed. */
export function bindConnectedReplacementTarget(
  nodes: CanvasFlowNode[],
  imageNodeId: string,
  replacementTaskNodeId: string,
): CanvasFlowNode[] {
  const imageNode = nodes.find((node) => node.id === imageNodeId);
  if (imageNode?.data.node.kind !== "image") return nodes;
  const existingNodeIds = new Set(nodes.map((node) => node.id));
  let changed = false;
  const nextNodes = nodes.map((node) => {
    const task = node.data.node.replacement_task;
    if (node.id !== replacementTaskNodeId || node.data.node.kind !== "replacement_task" || !task) return node;
    if (task.subjects.some((subject) => subject.target_node_id === imageNodeId)) return node;
    const subjectIndex = task.subjects.findIndex((subject) => (
      !subject.target_node_id || !existingNodeIds.has(subject.target_node_id)
    ));
    if (subjectIndex < 0) return node;
    changed = true;
    const subjects = task.subjects.map((subject, index) => index === subjectIndex
      ? { ...withoutTargetNodeId(subject), target_node_id: imageNodeId }
      : subject);
    return {
      ...node,
      data: { node: {
        ...node.data.node,
        replacement_task: { ...task, subjects },
      } },
    };
  });
  return changed ? nextNodes : nodes;
}

export function mergeDuplicateReplacementTasks(
  nodes: CanvasFlowNode[],
  edges: CanvasFlowEdge[],
): { nodes: CanvasFlowNode[]; edges: CanvasFlowEdge[]; changed: boolean } {
  const imageNodeIds = new Set(nodes
    .filter((node) => node.data.node.kind === "image")
    .map((node) => node.id));
  let bindingChanged = false;
  const nodesWithBindings = nodes.map((node) => {
    const task = node.data.node.replacement_task;
    if (node.data.node.kind !== "replacement_task" || !task) return node;
    const connectedImageIds = [...new Set(edges
      .filter((edge) => edge.target === node.id && imageNodeIds.has(edge.source))
      .map((edge) => edge.source))];
    const claimedImageIds = new Set(task.subjects
      .map((subject) => subject.target_node_id)
      .filter((targetNodeId): targetNodeId is string => Boolean(targetNodeId && imageNodeIds.has(targetNodeId))));
    const availableImageIds = connectedImageIds.filter((imageNodeId) => !claimedImageIds.has(imageNodeId));
    let nextImageIndex = 0;
    let nodeBindingChanged = false;
    const subjects = task.subjects.map((subject) => {
      if (subject.target_node_id && imageNodeIds.has(subject.target_node_id)) return subject;
      if (nextImageIndex >= availableImageIds.length) {
        if (!subject.target_node_id) return subject;
        nodeBindingChanged = true;
        bindingChanged = true;
        return withoutTargetNodeId(subject);
      }
      const targetNodeId = availableImageIds[nextImageIndex];
      nextImageIndex += 1;
      nodeBindingChanged = true;
      bindingChanged = true;
      return { ...withoutTargetNodeId(subject), target_node_id: targetNodeId };
    });
    if (!nodeBindingChanged) return node;
    return {
      ...node,
      data: { node: {
        ...node.data.node,
        replacement_task: { ...task, subjects },
      } },
    };
  });
  const canonicalByKey = new Map<string, CanvasFlowNode>();
  const duplicateToCanonical = new Map<string, string>();
  const latestByCanonical = new Map<string, CanvasFlowNode>();
  for (const node of nodesWithBindings) {
    const task = node.data.node.replacement_task;
    if (node.data.node.kind !== "replacement_task" || !task) continue;
    const key = `${task.shot_collection_node_id}:${task.source_object_id}`;
    const canonical = canonicalByKey.get(key);
    if (!canonical) {
      canonicalByKey.set(key, node);
      continue;
    }
    duplicateToCanonical.set(node.id, canonical.id);
    latestByCanonical.set(canonical.id, node);
  }
  if (!duplicateToCanonical.size) {
    return { nodes: nodesWithBindings, edges, changed: bindingChanged };
  }

  const mergedNodes = nodesWithBindings.filter((node) => !duplicateToCanonical.has(node.id)).map((node) => {
    const latest = latestByCanonical.get(node.id);
    const canonicalTask = node.data.node.replacement_task;
    const latestTask = latest?.data.node.replacement_task;
    if (!latest || !canonicalTask || !latestTask) return node;
    return {
      ...node,
      data: { node: {
        ...latest.data.node,
        id: node.id,
        x: node.position.x,
        y: node.position.y,
        replacement_task: {
          ...latestTask,
          target_description: canonicalTask.target_description || latestTask.target_description,
          shot_prompts: canonicalTask.shot_prompts.length ? canonicalTask.shot_prompts : latestTask.shot_prompts,
          output_shot_collection_node_id: canonicalTask.output_shot_collection_node_id || latestTask.output_shot_collection_node_id,
        },
        operation: node.data.node.operation ?? latest.data.node.operation,
      } },
    };
  });
  const nodeById = new Map(mergedNodes.map((node) => [node.id, node]));
  const edgeKeys = new Set<string>();
  const mergedEdges: CanvasFlowEdge[] = [];
  for (const edge of edges) {
    const source = duplicateToCanonical.get(edge.source) ?? edge.source;
    const target = duplicateToCanonical.get(edge.target) ?? edge.target;
    if (source === target) continue;
    const targetTask = nodeById.get(target)?.data.node.replacement_task;
    const sourceNode = nodeById.get(source)?.data.node;
    if (targetTask && sourceNode?.kind === "replaceable_analysis" && source !== targetTask.analysis_node_id) continue;
    if (targetTask && sourceNode?.kind === "shot_collection" && sourceNode.derived_kind === "shot" && source !== targetTask.shot_collection_node_id) continue;
    const key = `${source}:${target}:${edge.sourceHandle ?? ""}:${edge.targetHandle ?? ""}`;
    if (edgeKeys.has(key)) continue;
    edgeKeys.add(key);
    mergedEdges.push({
      ...edge,
      id: createEdgeId({ source, target, sourceHandle: edge.sourceHandle ?? null, targetHandle: edge.targetHandle ?? null }),
      source,
      target,
    });
  }
  return { nodes: mergedNodes, edges: mergedEdges, changed: true };
}
