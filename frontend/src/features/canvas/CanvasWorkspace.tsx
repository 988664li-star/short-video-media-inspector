import {
  addEdge,
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
  MarkerType,
  ReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type NodeMouseHandler,
  type ReactFlowInstance,
  type Viewport,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { MousePointer2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  analyzeCanvasReplaceables,
  extractCanvasMedia,
  extractCanvasVideoKeyframes,
  generateCanvasImage,
  generateCanvasText,
  splitCanvasVideoByShots,
} from "../../api/canvasProjects";
import type {
  CanvasAsset,
  CanvasDocument,
  CanvasEdge,
  CanvasMediaExtractionResult,
  CanvasNode,
  CanvasNodeKind,
  CanvasNodeOperation,
  CanvasReplacementTask,
  CanvasReplaceableObject,
  CanvasViewport,
} from "../../types/canvas";
import { CanvasMediaPreview } from "./CanvasMediaPreview";
import { CanvasNodeToolbar } from "./CanvasNodeToolbar";
import { CanvasEdge as CanvasEdgeView } from "./edges/CanvasEdge";
import { AudioNode } from "./nodes/AudioNode";
import { CanvasNodeActionsProvider } from "./nodes/CanvasNodeActions";
import { ExtractorNode } from "./nodes/ExtractorNode";
import { ImageNode } from "./nodes/ImageNode";
import { createCanvasNodeId } from "./nodes/nodeId";
import { ShotCollectionNode } from "./nodes/ShotCollectionNode";
import { ReplaceableAnalysisNode } from "./nodes/ReplaceableAnalysisNode";
import { ReplacementTaskNode } from "./nodes/ReplacementTaskNode";
import { TextNode } from "./nodes/TextNode";
import type { CanvasFlowEdge, CanvasFlowNode } from "./nodes/flowTypes";
import { VideoNode } from "./nodes/VideoNode";
import "./nodes/canvas-special-nodes.css";

interface CanvasWorkspaceProps {
  projectId: string;
  document: CanvasDocument;
  onDocumentChange: (document: CanvasDocument) => void;
  onUploadAsset: (file: File) => Promise<CanvasAsset>;
}

const nodeTypes = {
  text: TextNode,
  image: ImageNode,
  video: VideoNode,
  shot_collection: ShotCollectionNode,
  replaceable_analysis: ReplaceableAnalysisNode,
  replacement_task: ReplacementTaskNode,
  extractor: ExtractorNode,
  music: AudioNode,
  audio: AudioNode,
};

const edgeTypes = {
  canvas: CanvasEdgeView,
};

const defaultEdgeOptions = {
  type: "canvas",
  animated: false,
  markerEnd: { type: MarkerType.ArrowClosed, color: "#66d0b1", width: 16, height: 16 },
};

const TEXT_MODEL = "Qwen/Qwen3.6-27B";
const IMAGE_MODEL = "doubao-seedream-5-0-260128";

function initialOperation(kind: CanvasNodeKind): CanvasNodeOperation {
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

function nodeTitle(kind: CanvasNodeKind) {
  const titles: Record<CanvasNodeKind, string> = {
    text: "文本",
    image: "图片素材",
    video: "视频素材",
    shot_collection: "分镜组",
    replaceable_analysis: "可替换对象分析",
    replacement_task: "镜头替换任务",
    extractor: "链接提取",
    music: "作品配乐",
    audio: "视频混合音频",
  };
  return titles[kind];
}

function extractedMediaNodes(
  result: CanvasMediaExtractionResult,
  extractorId: string,
  position: { x: number; y: number },
): CanvasNode[] {
  const video = result.outputs.video;
  const music = result.outputs.music;
  const audio = result.outputs.audio;
  const specs: Array<{
    kind: "video" | "music" | "audio";
    title: string;
    detail: string;
    asset: CanvasAsset;
  }> = [];

  if (video.available && video.asset) {
    specs.push({
      kind: "video",
      title: "原视频",
      detail: result.description.slice(0, 600),
      asset: video.asset,
    });
  }
  if (music.available && music.asset && audio.available && audio.asset && music.asset.id === audio.asset.id) {
    specs.push({
      kind: "audio",
      title: "视频混合音频",
      detail: "平台只返回一条音频流；其中可能同时包含人声与背景音乐。",
      asset: audio.asset,
    });
  } else {
    if (music.available && music.asset) {
      specs.push({ kind: "music", title: "作品配乐", detail: music.message, asset: music.asset });
    }
    if (audio.available && audio.asset) {
      specs.push({ kind: "audio", title: "视频混合音频", detail: audio.message, asset: audio.asset });
    }
  }

  return specs.map((spec, index) => ({
    id: createCanvasNodeId(),
    kind: spec.kind,
    x: position.x + 470,
    y: position.y - 120 + index * 230,
    title: spec.title,
    detail: spec.detail,
    content: "",
    asset_id: spec.asset.id,
    asset_url: spec.asset.url,
    asset_name: spec.asset.filename,
    source_extractor_id: extractorId,
    availability_message: spec.detail,
    operation: initialOperation(spec.kind),
  }));
}

function toFlowNode(node: CanvasNode): CanvasFlowNode {
  const normalizedNode = {
    ...node,
    operation: node.operation ?? initialOperation(node.kind),
  };
  return {
    id: node.id,
    type: node.kind,
    position: { x: node.x, y: node.y },
    data: { node: normalizedNode },
  };
}

function toCanvasNode(node: CanvasFlowNode): CanvasNode {
  return {
    ...node.data.node,
    x: node.position.x,
    y: node.position.y,
  };
}

function toFlowEdge(edge: CanvasEdge): CanvasFlowEdge {
  return { ...edge, ...defaultEdgeOptions };
}

function toCanvasEdge(edge: CanvasFlowEdge): CanvasEdge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle ?? undefined,
    targetHandle: edge.targetHandle ?? undefined,
  };
}

function createEdgeId(connection: Connection) {
  return `edge-${connection.source}-${connection.target}-${createCanvasNodeId().replace("node-", "")}`;
}

function formatVideoTime(seconds: number) {
  const total = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function replaceableKindLabel(kind: CanvasReplaceableObject["kind"]) {
  return {
    product: "商品",
    person: "人物",
    background: "背景",
    text: "文字",
    other: "对象",
  }[kind];
}

function buildShotReplacementPrompt(
  task: CanvasReplacementTask,
  shotIndex: number,
  targetImageCount: number,
) {
  const action = task.actions.find((item) => item.shot_index === shotIndex)?.description
    || `${task.source_object_name} 出现在当前镜头中，保持原有位置、动作与遮挡关系。`;
  const targetReference = targetImageCount
    ? `@图片1${targetImageCount > 1 ? ` 至 @图片${targetImageCount}` : ""}`
    : "已连接的目标参考素材";
  const targetDescription = task.target_description.trim() || "以目标参考素材中的外观、结构、颜色和材质为准";
  return [
    "任务：替换 @视频1 中指定的源对象。",
    "",
    `目标对象：${targetReference}。${targetDescription}。`,
    `源对象：${task.source_object_name}${task.source_object_description ? `（${task.source_object_description}）` : ""}。`,
    "",
    `当前镜头：${action}`,
    `替换动作：将当前镜头中的“${task.source_object_name}”替换为目标对象。`,
    "",
    "保留规则：只替换上述对象。保持原视频的镜头顺序、动作、运镜、人物、背景、构图、遮挡关系、光线和所有未提及内容不变。目标对象在本任务所有镜头中必须保持为同一对象，外观、颜色、结构和细节一致，并保持原画面中的交互状态。",
    "",
    "输出规则：高清、自然色彩、稳定画面、连贯动作。不要新增场景、字幕、文字、水印或 Logo；不要变形、穿模、卡顿或改变未替换内容。",
  ].join("\n");
}

export function CanvasWorkspace({ projectId, document, onDocumentChange, onUploadAsset }: CanvasWorkspaceProps) {
  const [nodes, setNodes, applyNodesChange] = useNodesState<CanvasFlowNode>(document.nodes.map(toFlowNode));
  const [edges, setEdges, applyEdgesChange] = useEdgesState<CanvasFlowEdge>((document.edges ?? []).map(toFlowEdge));
  const [viewport, setViewport] = useState<CanvasViewport>(() => document.viewport);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<CanvasFlowNode, CanvasFlowEdge> | null>(null);
  const [previewNode, setPreviewNode] = useState<CanvasNode | null>(null);
  const [uploadingNodeId, setUploadingNodeId] = useState<string | null>(null);
  const [videoAction, setVideoAction] = useState<{ nodeId: string; type: "split" | "keyframes" } | null>(null);
  const [replacementAnalysisNodeId, setReplacementAnalysisNodeId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState("");
  const canvasElement = useRef<HTMLDivElement>(null);
  const saveTimer = useRef<number | null>(null);
  const documentChange = useRef(onDocumentChange);
  const dirty = useRef(false);

  useEffect(() => {
    documentChange.current = onDocumentChange;
  }, [onDocumentChange]);

  useEffect(() => {
    if (!dirty.current) return;
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      dirty.current = false;
      documentChange.current({
        nodes: nodes.map(toCanvasNode),
        edges: edges.map(toCanvasEdge),
        viewport,
      });
    }, 320);
    return () => {
      if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    };
  }, [edges, nodes, viewport]);

  const markDirty = () => {
    dirty.current = true;
  };

  const onNodesChange = useCallback((changes: NodeChange<CanvasFlowNode>[]) => {
    if (changes.some((change) => change.type === "position" || change.type === "remove")) markDirty();
    applyNodesChange(changes);
  }, [applyNodesChange]);

  const onEdgesChange = useCallback((changes: EdgeChange<CanvasFlowEdge>[]) => {
    if (changes.some((change) => change.type === "remove" || change.type === "replace")) markDirty();
    applyEdgesChange(changes);
  }, [applyEdgesChange]);

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return;
    markDirty();
    setEdges((current) => addEdge({
      ...connection,
      id: createEdgeId(connection),
      ...defaultEdgeOptions,
    }, current));
  }, [setEdges]);

  const updateText = useCallback((nodeId: string, content: string) => {
    markDirty();
    setNodes((current) => current.map((node) => node.id === nodeId ? {
      ...node,
      data: {
        node: {
          ...node.data.node,
          content,
          detail: content || "输入文本内容",
        },
      },
    } : node));
  }, [setNodes]);

  const updateOperation = useCallback((nodeId: string, patch: Partial<CanvasNodeOperation>) => {
    markDirty();
    setNodes((current) => current.map((node) => node.id === nodeId ? {
      ...node,
      data: {
        node: {
          ...node.data.node,
          operation: {
            ...(node.data.node.operation ?? initialOperation(node.data.node.kind)),
            ...patch,
          },
        },
      },
    } : node));
  }, [setNodes]);

  const saveNodeInstruction = useCallback((nodeId: string) => {
    const node = nodes.find((item) => item.id === nodeId)?.data.node;
    const prompt = node?.operation?.prompt.trim() ?? "";
    if (!prompt) {
      updateOperation(nodeId, { status: "failed", error: "请先填写处理指令" });
      return;
    }
    updateOperation(nodeId, { status: "succeeded", error: "" });
  }, [nodes, updateOperation]);

  const uploadNodeAsset = useCallback(async (
    nodeId: string,
    kind: "image" | "video",
    file: File,
  ) => {
    if (uploadingNodeId) return;
    setUploadingNodeId(nodeId);
    setUploadError("");
    try {
      const asset = await onUploadAsset(file);
      markDirty();
      setNodes((current) => current.map((node) => node.id === nodeId ? {
        ...node,
        data: {
          node: {
            ...node.data.node,
            kind,
            title: asset.filename,
            detail: "本地上传素材",
            asset_id: asset.id,
            asset_url: asset.url,
            asset_name: asset.filename,
          },
        },
      } : node));
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "上传素材失败");
    } finally {
      setUploadingNodeId(null);
    }
  }, [onUploadAsset, setNodes, uploadingNodeId]);

  const uploadReferenceAsset = useCallback(async (nodeId: string, file: File) => {
    if (uploadingNodeId) return;
    setUploadingNodeId(nodeId);
    setUploadError("");
    try {
      const asset = await onUploadAsset(file);
      markDirty();
      setNodes((current) => current.map((node) => node.id === nodeId ? {
        ...node,
        data: {
          node: {
            ...node.data.node,
            reference_assets: [
              ...(node.data.node.reference_assets ?? []).filter((item) => item.id !== asset.id),
              { id: asset.id, url: asset.url, filename: asset.filename, mime_type: asset.mime_type },
            ],
          },
        },
      } : node));
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "上传参考素材失败");
    } finally {
      setUploadingNodeId(null);
    }
  }, [onUploadAsset, setNodes, uploadingNodeId]);

  const getUpstreamNodes = useCallback((nodeId: string) => edges
    .filter((edge) => edge.target === nodeId)
    .map((edge) => nodes.find((node) => node.id === edge.source)?.data.node)
    .filter((node): node is CanvasNode => Boolean(node)), [edges, nodes]);

  const runNode = useCallback(async (nodeId: string) => {
    const flowNode = nodes.find((node) => node.id === nodeId);
    if (!flowNode || !["text", "image"].includes(flowNode.data.node.kind)) return;
    const canvasNode = flowNode.data.node;
    const operation = canvasNode.operation ?? initialOperation(canvasNode.kind);
    const prompt = operation.prompt.trim();
    if (!prompt) {
      updateOperation(nodeId, { status: "failed", error: "请先输入生成提示词" });
      return;
    }
    updateOperation(nodeId, { status: "running", error: "" });
    const upstreamNodes = getUpstreamNodes(nodeId);
    try {
      if (canvasNode.kind === "text") {
        const context = upstreamNodes.map((node) => {
          if (node.kind === "text") return node.content;
          if (node.kind === "shot_collection") {
            return `[分镜组：${node.shot_assets?.length ?? 0} 个连续镜头，已按原时间顺序保留，可作为多镜头处理输入]`;
          }
          return node.asset_name ? `[${node.kind === "image" ? "图片" : "视频"}素材：${node.asset_name}]` : "";
        }).filter(Boolean).join("\n\n");
        const result = await generateCanvasText(projectId, prompt, context);
        markDirty();
        setNodes((current) => current.map((node) => node.id === nodeId ? {
          ...node,
          data: {
            node: {
              ...node.data.node,
              content: result.content,
              detail: result.content,
              operation: {
                ...(node.data.node.operation ?? initialOperation("text")),
                model: result.model,
                status: "succeeded",
                error: "",
              },
            },
          },
        } : node));
        return;
      }
      const selectedReferenceIds = new Set(operation.referenced_asset_ids ?? []);
      const sourceAssetIds = [
        canvasNode.asset_id,
        ...(canvasNode.reference_assets ?? [])
          .filter((asset) => selectedReferenceIds.has(asset.id) && asset.mime_type.startsWith("image/"))
          .map((asset) => asset.id),
        ...upstreamNodes.filter((node) => node.kind === "image").map((node) => node.asset_id),
      ].filter((assetId): assetId is string => Boolean(assetId));
      const styleInstruction = operation.style && operation.style !== "自然" ? `\n\n画面风格：${operation.style}。` : "";
      const roleInstruction = operation.role_mode === "锁定人物" ? "\n\n人物要求：如画面中有人物，保持同一人物的身份与外观一致。" : "";
      const result = await generateCanvasImage(
        projectId,
        `${prompt}${styleInstruction}${roleInstruction}`,
        operation.source_url?.trim() ?? "",
        [...new Set(sourceAssetIds)],
        operation.aspect_ratio || "原比例",
      );
      markDirty();
      setNodes((current) => current.map((node) => node.id === nodeId ? {
        ...node,
        data: {
          node: {
            ...node.data.node,
            title: result.asset.filename,
            detail: "AI 生成图片",
            asset_id: result.asset.id,
            asset_url: result.asset.url,
            asset_name: result.asset.filename,
            operation: {
              ...(node.data.node.operation ?? initialOperation("image")),
              model: result.model,
              status: "succeeded",
              error: "",
            },
          },
        },
      } : node));
    } catch (error) {
      updateOperation(nodeId, {
        status: "failed",
        error: error instanceof Error ? error.message : "节点运行失败",
      });
    }
  }, [getUpstreamNodes, nodes, projectId, setNodes, updateOperation]);

  const runExtractor = useCallback(async (nodeId: string) => {
    const sourceNode = nodes.find((node) => node.id === nodeId);
    if (!sourceNode || sourceNode.data.node.kind !== "extractor") return;
    const shareText = sourceNode.data.node.content.trim();
    if (!shareText) {
      updateOperation(nodeId, { status: "failed", error: "请先粘贴抖音或 TikTok 分享链接" });
      return;
    }
    if (sourceNode.data.node.operation?.status === "running") return;
    updateOperation(nodeId, { status: "running", error: "" });
    try {
      const result = await extractCanvasMedia(projectId, shareText);
      const existingOutputIds = new Set(
        nodes
          .filter((node) => node.data.node.source_extractor_id === nodeId)
          .map((node) => node.id),
      );
      const outputNodes = extractedMediaNodes(result, nodeId, sourceNode.position).map(toFlowNode);
      const outputEdges = outputNodes.map((targetNode) => ({
        id: createEdgeId({
          source: nodeId,
          target: targetNode.id,
          sourceHandle: "output",
          targetHandle: "input",
        }),
        source: nodeId,
        target: targetNode.id,
        sourceHandle: "output",
        targetHandle: "input",
        ...defaultEdgeOptions,
      }));
      const warning = result.warnings[0] ? ` · ${result.warnings[0]}` : "";
      markDirty();
      setNodes((current) => [
        ...current
          .filter((node) => !existingOutputIds.has(node.id))
          .map((node) => node.id === nodeId ? {
            ...node,
            data: {
              node: {
                ...node.data.node,
                title: `${result.platform === "douyin" ? "抖音" : "TikTok"} · ${result.aweme_id}`,
                detail: `提取完成，已生成 ${outputNodes.length} 个实际返回的媒体节点${warning}`.slice(0, 600),
                operation: {
                  ...(node.data.node.operation ?? initialOperation("extractor")),
                  status: "succeeded" as const,
                  error: "",
                },
              },
            },
          } : node),
        ...outputNodes,
      ]);
      setEdges((current) => [
        ...current.filter((edge) => !existingOutputIds.has(edge.source) && !existingOutputIds.has(edge.target)),
        ...outputEdges,
      ]);
    } catch (error) {
      updateOperation(nodeId, {
        status: "failed",
        error: error instanceof Error ? error.message : "链接提取失败",
      });
    }
  }, [nodes, projectId, setEdges, setNodes, updateOperation]);

  const commitVideoOutputs = useCallback((
    nodeId: string,
    derivedKind: "shot" | "keyframe",
    outputs: CanvasFlowNode[],
    message: string,
  ) => {
    const previousOutputIds = new Set(
      nodes
        .filter((node) => node.data.node.source_node_id === nodeId && node.data.node.derived_kind === derivedKind)
        .map((node) => node.id),
    );
    const outputEdges = outputs.map((output) => ({
      id: createEdgeId({ source: nodeId, target: output.id, sourceHandle: "output", targetHandle: "input" }),
      source: nodeId,
      target: output.id,
      sourceHandle: "output",
      targetHandle: "input",
      ...defaultEdgeOptions,
    }));
    markDirty();
    setNodes((current) => [
      ...current
        .filter((node) => !previousOutputIds.has(node.id))
        .map((node) => node.id === nodeId ? {
          ...node,
          data: {
            node: {
              ...node.data.node,
              detail: message,
              operation: {
                ...(node.data.node.operation ?? initialOperation("video")),
                status: "succeeded" as const,
                error: "",
                message,
              },
            },
          },
        } : node),
      ...outputs,
    ]);
    setEdges((current) => [
      ...current.filter((edge) => !previousOutputIds.has(edge.source) && !previousOutputIds.has(edge.target)),
      ...outputEdges,
    ]);
  }, [nodes, setEdges, setNodes]);

  const splitVideoByShots = useCallback(async (nodeId: string) => {
    const source = nodes.find((node) => node.id === nodeId);
    const assetId = source?.data.node.asset_id;
    if (!source || !assetId || source.data.node.kind !== "video") {
      updateOperation(nodeId, { status: "failed", error: "请先上传或生成视频" });
      return;
    }
    if (videoAction) return;
    setVideoAction({ nodeId, type: "split" });
    updateOperation(nodeId, { status: "running", error: "", message: "正在按镜头检测并导出视频片段…" });
    try {
      const result = await splitCanvasVideoByShots(projectId, assetId);
      const outputNodes = [toFlowNode({
        id: createCanvasNodeId(),
        kind: "shot_collection",
        x: source.position.x + 450,
        y: source.position.y - 36,
        title: `分镜组 · ${result.shots.length} 个镜头`,
        detail: `完整保留 ${result.shots.length} 个连续镜头，按原时间顺序供后续多镜头处理使用`,
        content: "",
        source_node_id: nodeId,
        derived_kind: "shot",
        shot_assets: result.shots.map((shot) => ({
          index: shot.index,
          start_seconds: shot.start_seconds,
          end_seconds: shot.end_seconds,
          duration_seconds: shot.duration_seconds,
          asset_id: shot.asset.id,
          asset_url: shot.asset.url,
          asset_name: shot.asset.filename,
        })),
        operation: initialOperation("shot_collection"),
      })];
      commitVideoOutputs(nodeId, "shot", outputNodes, `已切出 ${result.shots.length} 个镜头，并归入一个分镜组`);
    } catch (error) {
      updateOperation(nodeId, {
        status: "failed",
        error: error instanceof Error ? error.message : "视频分镜失败",
      });
    } finally {
      setVideoAction(null);
    }
  }, [commitVideoOutputs, nodes, projectId, updateOperation, videoAction]);

  const extractVideoKeyframes = useCallback(async (nodeId: string) => {
    const source = nodes.find((node) => node.id === nodeId);
    const assetId = source?.data.node.asset_id;
    if (!source || !assetId || source.data.node.kind !== "video") {
      updateOperation(nodeId, { status: "failed", error: "请先上传或生成视频" });
      return;
    }
    if (videoAction) return;
    setVideoAction({ nodeId, type: "keyframes" });
    updateOperation(nodeId, { status: "running", error: "", message: "正在按镜头提取关键帧…" });
    try {
      const result = await extractCanvasVideoKeyframes(projectId, assetId);
      const outputNodes = result.frames.map((frame, index) => toFlowNode({
        id: createCanvasNodeId(),
        kind: "image",
        x: source.position.x + 450 + (index % 2) * 350,
        y: source.position.y - 100 + Math.floor(index / 2) * 260,
        title: `镜头 ${String(frame.shot_index).padStart(2, "0")} · 关键帧`,
        detail: `${formatVideoTime(frame.timestamp_seconds)} 抽取的关键帧`,
        content: "",
        asset_id: frame.asset.id,
        asset_url: frame.asset.url,
        asset_name: frame.asset.filename,
        source_node_id: nodeId,
        derived_kind: "keyframe",
        operation: initialOperation("image"),
      }));
      commitVideoOutputs(nodeId, "keyframe", outputNodes, `已抽取 ${outputNodes.length} 张关键帧图片`);
    } catch (error) {
      updateOperation(nodeId, {
        status: "failed",
        error: error instanceof Error ? error.message : "视频抽帧失败",
      });
    } finally {
      setVideoAction(null);
    }
  }, [commitVideoOutputs, nodes, projectId, updateOperation, videoAction]);

  const analyzeReplaceables = useCallback(async (nodeId: string) => {
    const source = nodes.find((node) => node.id === nodeId);
    const shots = source?.data.node.shot_assets ?? [];
    if (!source || source.data.node.kind !== "shot_collection" || !shots.length) {
      updateOperation(nodeId, { status: "failed", error: "请先完成视频分镜，得到至少一个镜头片段" });
      return;
    }
    if (replacementAnalysisNodeId) return;
    setReplacementAnalysisNodeId(nodeId);
    updateOperation(nodeId, { status: "running", error: "", message: "正在抽取镜头关键帧并识别可替换对象…" });
    try {
      const result = await analyzeCanvasReplaceables(projectId, shots);
      const existingOutputIds = new Set(nodes
        .filter((node) => node.data.node.kind === "replaceable_analysis" && node.data.node.source_node_id === nodeId)
        .map((node) => node.id));
      const analysisNode = toFlowNode({
        id: createCanvasNodeId(),
        kind: "replaceable_analysis",
        x: source.position.x + 510,
        y: source.position.y - 12,
        title: `可替换对象 · ${result.objects.length} 项`,
        detail: `已基于 ${result.keyframes.length} 个镜头关键帧完成对象识别`,
        content: "",
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
              detail: `已识别 ${result.objects.length} 个可替换对象；选择对象后可创建镜头替换任务`,
              operation: {
                ...(node.data.node.operation ?? initialOperation("shot_collection")),
                status: "succeeded" as const,
                error: "",
                message: `已识别 ${result.objects.length} 个可替换对象`,
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
  }, [nodes, projectId, replacementAnalysisNodeId, setEdges, setNodes, updateOperation]);

  const createReplacementTask = useCallback((analysisNodeId: string, objectId: string) => {
    const analysisFlowNode = nodes.find((node) => node.id === analysisNodeId);
    const analysis = analysisFlowNode?.data.node;
    const sourceNodeId = analysis?.source_node_id;
    const sourceGroup = nodes.find((node) => node.id === sourceNodeId)?.data.node;
    const sourceObject = analysis?.replaceable_objects?.find((item) => item.id === objectId);
    if (!analysisFlowNode || !analysis || !sourceNodeId || !sourceGroup || !sourceObject) return;

    const existing = nodes.find((node) => node.data.node.kind === "replacement_task"
      && node.data.node.replacement_task?.analysis_node_id === analysisNodeId
      && node.data.node.replacement_task?.source_object_id === objectId);
    if (existing) {
      setNodes((current) => current.map((node) => ({ ...node, selected: node.id === existing.id })));
      return;
    }

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
      shot_prompts: sourceObject.shot_indices.map((shotIndex) => ({ shot_index: shotIndex, prompt: "", status: "pending" })),
    };
    const taskNode = toFlowNode({
      id: createCanvasNodeId(),
      kind: "replacement_task",
      x: analysisFlowNode.position.x + 500,
      y: analysisFlowNode.position.y + 8,
      title: `${replaceableKindLabel(sourceObject.kind)}替换 · ${sourceObject.name}`,
      detail: `覆盖 ${sourceObject.shot_indices.length} 个镜头；连接目标${replaceableKindLabel(sourceObject.kind)}素材后生成逐镜头提示词`,
      content: "",
      replacement_task: task,
      operation: initialOperation("replacement_task"),
    });
    const connections = [sourceNodeId, analysisNodeId].map((source) => toFlowEdge({
      id: createEdgeId({ source, target: taskNode.id, sourceHandle: "output", targetHandle: "input" }),
      source,
      target: taskNode.id,
      sourceHandle: "output",
      targetHandle: "input",
    }));
    markDirty();
    setNodes((current) => [...current.map((node) => ({ ...node, selected: false })), { ...taskNode, selected: true }]);
    setEdges((current) => [...current, ...connections]);
  }, [nodes, setEdges, setNodes]);

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

  const updateReplacementShotPrompt = useCallback((nodeId: string, shotIndex: number, prompt: string) => {
    const task = nodes.find((node) => node.id === nodeId)?.data.node.replacement_task;
    if (!task) return;
    updateReplacementTask(nodeId, {
      shot_prompts: task.shot_prompts.map((item) => item.shot_index === shotIndex
        ? { ...item, prompt, status: prompt.trim() ? "ready" : "pending" }
        : item),
    });
  }, [nodes, updateReplacementTask]);

  const buildReplacementPrompts = useCallback((nodeId: string) => {
    const flowNode = nodes.find((node) => node.id === nodeId);
    const task = flowNode?.data.node.replacement_task;
    if (!flowNode || !task) return;
    const targetImageCount = getUpstreamNodes(nodeId).filter((node) => node.kind === "image" && node.asset_id).length;
    if (!targetImageCount) {
      updateOperation(nodeId, { status: "failed", error: "请先连接至少一个目标图片节点，再生成逐镜头提示词" });
      return;
    }
    updateReplacementTask(nodeId, {
      shot_prompts: task.shot_indices.map((shotIndex) => ({
        shot_index: shotIndex,
        prompt: buildShotReplacementPrompt(task, shotIndex, targetImageCount),
        status: "ready",
      })),
    });
    updateOperation(nodeId, {
      status: "succeeded",
      error: "",
      message: `已生成 ${task.shot_indices.length} 条可审查的逐镜头替换提示词`,
    });
  }, [getUpstreamNodes, nodes, updateOperation, updateReplacementTask]);

  const nodeActions = useMemo(() => ({
    updateText,
    updateOperation,
    saveNodeInstruction,
    uploadNodeAsset,
    uploadReferenceAsset,
    uploadingNodeId,
    splitVideoByShots,
    extractVideoKeyframes,
    videoAction,
    analyzeReplaceables,
    replacementAnalysisNodeId,
    createReplacementTask,
    updateReplacementTask,
    updateReplacementShotPrompt,
    buildReplacementPrompts,
    runNode,
    runExtractor,
    getUpstreamNodes,
    previewMedia: setPreviewNode,
  }), [analyzeReplaceables, buildReplacementPrompts, createReplacementTask, extractVideoKeyframes, getUpstreamNodes, replacementAnalysisNodeId, runExtractor, runNode, saveNodeInstruction, splitVideoByShots, updateOperation, updateReplacementShotPrompt, updateReplacementTask, updateText, uploadNodeAsset, uploadReferenceAsset, uploadingNodeId, videoAction]);

  const nextNodePosition = useCallback(() => {
    const element = canvasElement.current;
    if (!element || !flowInstance) return { x: 120 + nodes.length * 24, y: 120 + nodes.length * 20 };
    const rect = element.getBoundingClientRect();
    const position = flowInstance.screenToFlowPosition({
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    });
    const stagger = (nodes.length % 6) * 24;
    return { x: position.x - 130 + stagger, y: position.y - 90 + stagger };
  }, [flowInstance, nodes.length]);

  const addNode = useCallback((kind: CanvasNodeKind) => {
    const position = nextNodePosition();
    const canvasNode: CanvasNode = {
      id: createCanvasNodeId(),
      kind,
      x: position.x,
      y: position.y,
      title: nodeTitle(kind),
      detail: kind === "text"
        ? "输入文本内容"
        : kind === "extractor"
          ? "输入分享链接，自动生成实际返回的媒体节点"
          : kind === "image"
            ? "上传参考图，或直接输入提示词生成"
            : kind === "video"
              ? "上传视频，或直接配置视频创作指令"
              : "点击预览按钮查看素材",
      content: "",
      operation: initialOperation(kind),
    };
    markDirty();
    setNodes((current) => [
      ...current.map((node) => ({ ...node, selected: false })),
      { ...toFlowNode(canvasNode), selected: true },
    ]);
  }, [nextNodePosition, setNodes]);

  const onMoveEnd = useCallback((_: MouseEvent | TouchEvent | null, nextViewport: Viewport) => {
    markDirty();
    setViewport({ x: nextViewport.x, y: nextViewport.y, scale: nextViewport.zoom });
  }, []);

  // Video actions live above the node. When a video sits against the canvas top,
  // move the viewport just enough to keep that action bar fully usable.
  const onNodeClick: NodeMouseHandler<CanvasFlowNode> = useCallback((_, node) => {
    if (node.data.node.kind !== "video" || !flowInstance) return;

    const nodeTopInView = node.position.y * viewport.scale + viewport.y;
    const minimumTop = 78;
    if (nodeTopInView >= minimumTop) return;

    const nextViewport = {
      x: viewport.x,
      y: viewport.y + (minimumTop - nodeTopInView),
      zoom: viewport.scale,
    };
    void flowInstance.setViewport(nextViewport, { duration: 180 });
    markDirty();
    setViewport({ x: nextViewport.x, y: nextViewport.y, scale: nextViewport.zoom });
  }, [flowInstance, viewport]);

  return (
    <section className="creative-canvas" aria-label="无限画布" data-project-id={projectId}>
      <div ref={canvasElement} className="creative-canvas__layout">
        <CanvasNodeToolbar
          onAddText={() => addNode("text")}
          onAddExtractor={() => addNode("extractor")}
          onAddImage={() => addNode("image")}
          onAddVideo={() => addNode("video")}
        />
        <div className="creative-canvas__hint"><MousePointer2 /> 拖动节点标题移动 · 从连接点拖出连线 · Delete 删除</div>
        <CanvasNodeActionsProvider value={nodeActions}>
          <ReactFlow<CanvasFlowNode, CanvasFlowEdge>
            className="creative-canvas__flow"
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            defaultViewport={{ x: viewport.x, y: viewport.y, zoom: viewport.scale }}
            minZoom={0.1}
            maxZoom={2.5}
            connectionMode={ConnectionMode.Strict}
            connectionRadius={28}
            connectOnClick
            deleteKeyCode={["Backspace", "Delete"]}
            multiSelectionKeyCode="Control"
            selectionKeyCode="Shift"
            panOnScroll
            zoomOnScroll={false}
            proOptions={{ hideAttribution: true }}
            onInit={setFlowInstance}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onMoveEnd={onMoveEnd}
            isValidConnection={(connection) => connection.source !== connection.target}
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} color="rgba(130, 159, 199, .28)" />
            <Controls position="bottom-right" showInteractive={false} />
          </ReactFlow>
        </CanvasNodeActionsProvider>
        {uploadError ? <p className="creative-canvas__upload-error" role="alert">{uploadError}</p> : null}
      </div>
      <CanvasMediaPreview node={previewNode} onClose={() => setPreviewNode(null)} />
    </section>
  );
}
