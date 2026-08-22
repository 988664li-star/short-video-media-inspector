import {
  addEdge,
  applyNodeChanges,
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
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

import { listCanvasVideoModels } from "../../api/canvasProjects";
import type {
  CanvasAsset,
  CanvasDocument,
  CanvasNode,
  CanvasNodeKind,
  CanvasNodeOperation,
  CanvasViewport,
  CanvasVideoModel,
} from "../../types/canvas";
import { CanvasMediaPreview } from "./CanvasMediaPreview";
import { CanvasNodeToolbar } from "./CanvasNodeToolbar";
import { canvasEdgeTypes, canvasNodeTypes } from "./canvasFlowConfig";
import { useCanvasPersistence } from "./useCanvasPersistence";
import { useCanvasProcessing } from "./useCanvasProcessing";
import { useReplacementWorkflow } from "./useReplacementWorkflow";
import {
  bindConnectedReplacementTarget,
  clearDeletedReplacementTargetBindings,
  createEdgeId,
  createCanvasNode,
  defaultCanvasEdgeOptions as defaultEdgeOptions,
  initialOperation,
  toFlowEdge,
  toFlowNode,
} from "./canvasDocument";
import { nextReferenceAssetLabel } from "./referenceAssets";
import { CanvasNodeActionsProvider } from "./nodes/CanvasNodeActions";
import type { CanvasFlowEdge, CanvasFlowNode } from "./nodes/flowTypes";
import "./nodes/canvas-special-nodes.css";

export interface CanvasWorkspaceProps {
  projectId: string;
  document: CanvasDocument;
  onDocumentChange: (document: CanvasDocument) => void;
  onUploadAsset: (file: File) => Promise<CanvasAsset>;
}

function isTextEditingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable
    || target.matches("input, textarea, select")
    || Boolean(target.closest("[contenteditable='true']"));
}

export function CanvasWorkspaceController({ projectId, document, onDocumentChange, onUploadAsset }: CanvasWorkspaceProps) {
  const [nodes, setNodes, applyNodesChange] = useNodesState<CanvasFlowNode>(document.nodes.map(toFlowNode));
  const [edges, setEdges, applyEdgesChange] = useEdgesState<CanvasFlowEdge>((document.edges ?? []).map(toFlowEdge));
  const [viewport, setViewport] = useState<CanvasViewport>(() => document.viewport);
  const viewportRef = useRef(viewport);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<CanvasFlowNode, CanvasFlowEdge> | null>(null);
  const [previewNode, setPreviewNode] = useState<CanvasNode | null>(null);
  const [uploadingNodeId, setUploadingNodeId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [videoModels, setVideoModels] = useState<CanvasVideoModel[]>([]);
  const canvasElement = useRef<HTMLDivElement>(null);
  const markDirty = useCanvasPersistence({
    projectId,
    document,
    nodes,
    edges,
    viewport,
    onDocumentChange,
    setNodes,
    setEdges,
  });

  useEffect(() => {
    let active = true;
    void listCanvasVideoModels().then(({ models }) => {
      if (active) setVideoModels(models);
    }).catch(() => {
      if (active) setVideoModels([]);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const selectAllNodes = (event: KeyboardEvent) => {
      if (
        event.isComposing
        || event.altKey
        || (!event.ctrlKey && !event.metaKey)
        || event.key.toLowerCase() !== "a"
        || isTextEditingTarget(event.target)
      ) return;

      event.preventDefault();
      setNodes((current) => {
        if (current.every((node) => node.selected)) return current;
        return current.map((node) => node.selected ? node : { ...node, selected: true });
      });
    };

    window.addEventListener("keydown", selectAllNodes);
    return () => window.removeEventListener("keydown", selectAllNodes);
  }, [setNodes]);

  const onNodesChange = useCallback((changes: NodeChange<CanvasFlowNode>[]) => {
    const deletedNodeIds = new Set(changes
      .filter((change): change is Extract<NodeChange<CanvasFlowNode>, { type: "remove" }> => change.type === "remove")
      .map((change) => change.id));
    if (changes.some((change) => change.type === "position" || change.type === "remove")) markDirty();
    if (!deletedNodeIds.size) {
      applyNodesChange(changes);
      return;
    }
    setNodes((current) => clearDeletedReplacementTargetBindings(
      applyNodeChanges(changes, current),
      deletedNodeIds,
    ));
  }, [applyNodesChange, markDirty, setNodes]);

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
    setNodes((current) => bindConnectedReplacementTarget(
      current,
      connection.source!,
      connection.target!,
    ));
  }, [markDirty, setEdges, setNodes]);

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
              {
                id: asset.id,
                url: asset.url,
                filename: asset.filename,
                mime_type: asset.mime_type,
                label: nextReferenceAssetLabel(node.data.node.reference_assets, asset.mime_type),
              },
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

  const updateReferenceAssetLabel = useCallback((nodeId: string, assetId: string, label: string) => {
    markDirty();
    setNodes((current) => current.map((node) => {
      if (node.id !== nodeId) return node;
      return {
        ...node,
        data: { node: {
          ...node.data.node,
          reference_assets: (node.data.node.reference_assets ?? []).map((asset) => (
            asset.id === assetId ? { ...asset, label: label.slice(0, 80) } : asset
          )),
        } },
      };
    }));
  }, [setNodes]);

  const getUpstreamNodes = useCallback((nodeId: string) => edges
    .filter((edge) => edge.target === nodeId)
    .map((edge) => nodes.find((node) => node.id === edge.source)?.data.node)
    .filter((node): node is CanvasNode => Boolean(node)), [edges, nodes]);

  const getCanvasNode = useCallback((nodeId: string | undefined): CanvasNode | undefined => (
    nodeId ? nodes.find((node) => node.id === nodeId)?.data.node : undefined
  ), [nodes]);

  const {
    runNode,
    runExtractor,
    videoAction,
    splitVideoByShots,
    extractVideoKeyframes,
    composeVideoComparison,
  } = useCanvasProcessing({
    projectId,
    nodes,
    setNodes,
    setEdges,
    markDirty,
    updateOperation,
    getUpstreamNodes,
  });

  const {
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
  } = useReplacementWorkflow({
    projectId,
    nodes,
    setNodes,
    setEdges,
    flowInstance,
    markDirty,
    updateOperation,
    getUpstreamNodes,
    videoModels,
  });
  const nodeActions = useMemo(() => ({
    videoModels,
    updateText,
    updateOperation,
    saveNodeInstruction,
    uploadNodeAsset,
    uploadReferenceAsset,
    updateReferenceAssetLabel,
    uploadingNodeId,
    splitVideoByShots,
    extractVideoKeyframes,
    composeVideoComparison,
    videoAction,
    analyzeReplaceables,
    replacementAnalysisNodeId,
    createReplacementTask,
    updateReplacementTask,
    toggleReplacementShot,
    updateReplacementShotPrompt,
    buildReplacementPrompts,
    submitReplacementTasks,
    refreshReplacementOutputGroup,
    composeReplacementOutputGroup,
    addTargetImageNode,
    runNode,
    runExtractor,
    getUpstreamNodes,
    getCanvasNode,
    previewMedia: setPreviewNode,
  }), [addTargetImageNode, analyzeReplaceables, buildReplacementPrompts, composeReplacementOutputGroup, composeVideoComparison, createReplacementTask, extractVideoKeyframes, getCanvasNode, getUpstreamNodes, refreshReplacementOutputGroup, replacementAnalysisNodeId, runExtractor, runNode, saveNodeInstruction, splitVideoByShots, submitReplacementTasks, toggleReplacementShot, updateOperation, updateReferenceAssetLabel, updateReplacementShotPrompt, updateReplacementTask, updateText, uploadNodeAsset, uploadReferenceAsset, uploadingNodeId, videoAction, videoModels]);

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
    const canvasNode = createCanvasNode(kind, position);
    markDirty();
    setNodes((current) => [
      ...current.map((node) => ({ ...node, selected: false })),
      { ...toFlowNode(canvasNode), selected: true },
    ]);
  }, [nextNodePosition, setNodes]);

  const onMoveEnd = useCallback((_: MouseEvent | TouchEvent | null, nextViewport: Viewport) => {
    const normalizedViewport = { x: nextViewport.x, y: nextViewport.y, scale: nextViewport.zoom };
    const currentViewport = viewportRef.current;
    if (Math.abs(currentViewport.x - normalizedViewport.x) < 0.01
      && Math.abs(currentViewport.y - normalizedViewport.y) < 0.01
      && Math.abs(currentViewport.scale - normalizedViewport.scale) < 0.0001) return;
    viewportRef.current = normalizedViewport;
    markDirty();
    setViewport(normalizedViewport);
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
    viewportRef.current = { x: nextViewport.x, y: nextViewport.y, scale: nextViewport.zoom };
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
        <div className="creative-canvas__hint"><MousePointer2 /> 空白处拖动框选 · Ctrl/⌘/Shift 点击多选 · Ctrl/⌘ A 全选 · 空格拖动画布</div>
        <CanvasNodeActionsProvider value={nodeActions}>
          <ReactFlow<CanvasFlowNode, CanvasFlowEdge>
            className="creative-canvas__flow"
            nodes={nodes}
            edges={edges}
            nodeTypes={canvasNodeTypes}
            edgeTypes={canvasEdgeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            defaultViewport={{ x: viewport.x, y: viewport.y, zoom: viewport.scale }}
            minZoom={0.1}
            maxZoom={2.5}
            connectionMode={ConnectionMode.Strict}
            connectionRadius={28}
            connectOnClick
            deleteKeyCode={["Backspace", "Delete"]}
            multiSelectionKeyCode={["Control", "Meta", "Shift"]}
            selectionKeyCode="Shift"
            selectionOnDrag
            panOnDrag={[1, 2]}
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
