import { useCallback, useState, type Dispatch, type SetStateAction } from "react";

import {
  composeCanvasVideoComparison,
  extractCanvasMedia,
  extractCanvasVideoKeyframes,
  generateCanvasImage,
  generateCanvasText,
  splitCanvasVideoByShots,
} from "../../api/canvasProjects";
import type { CanvasNode, CanvasNodeOperation, CanvasReferenceAsset } from "../../types/canvas";
import {
  createEdgeId,
  defaultCanvasEdgeOptions as defaultEdgeOptions,
  extractedMediaNodes,
  initialOperation,
  referenceAssetFromNode,
  toFlowNode,
} from "./canvasDocument";
import { createCanvasNodeId } from "./nodes/nodeId";
import type { CanvasFlowEdge, CanvasFlowNode } from "./nodes/flowTypes";
import { formatVideoTime } from "./replacementHelpers";
import {
  normalizeReferenceAssets,
  referenceAssetLabel,
  replaceInlineReferences,
  stripInlineReferences,
} from "./referenceAssets";

interface Options {
  projectId: string;
  nodes: CanvasFlowNode[];
  setNodes: Dispatch<SetStateAction<CanvasFlowNode[]>>;
  setEdges: Dispatch<SetStateAction<CanvasFlowEdge[]>>;
  markDirty: () => void;
  updateOperation: (nodeId: string, patch: Partial<CanvasNodeOperation>) => void;
  getUpstreamNodes: (nodeId: string) => CanvasNode[];
}

export function useCanvasProcessing({
  projectId, nodes, setNodes, setEdges, markDirty, updateOperation, getUpstreamNodes,
}: Options) {
  const [videoAction, setVideoAction] = useState<{ nodeId: string; type: "split" | "keyframes" | "compare" } | null>(null);

  const runNode = useCallback(async (nodeId: string, operationOverride?: Partial<CanvasNodeOperation>) => {
    const flowNode = nodes.find((node) => node.id === nodeId);
    if (!flowNode || !["text", "image"].includes(flowNode.data.node.kind)) return;
    const canvasNode = flowNode.data.node;
    const operation = {
      ...(canvasNode.operation ?? initialOperation(canvasNode.kind)),
      ...operationOverride,
    };
    const prompt = operation.prompt.trim();
    const promptText = stripInlineReferences(prompt).trim();
    if (!promptText) {
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
        const result = await generateCanvasText(projectId, promptText, context);
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
      const availableReferenceAssets = [
        ...normalizeReferenceAssets(canvasNode.reference_assets),
        ...upstreamNodes.flatMap((node) => [
          ...normalizeReferenceAssets(node.reference_assets),
          referenceAssetFromNode(node),
        ]),
      ].filter((asset): asset is CanvasReferenceAsset => Boolean(asset));
      const referenceAssetsById = new Map(availableReferenceAssets.map((asset) => [asset.id, asset]));
      const selectedReferenceAssets = [...selectedReferenceIds]
        .map((assetId) => referenceAssetsById.get(assetId))
        .filter((asset): asset is CanvasReferenceAsset => Boolean(asset))
        .filter((asset) => asset.mime_type.startsWith("image/"));
      const promptWithReferenceLabels = replaceInlineReferences(prompt, (assetId) => {
        const asset = referenceAssetsById.get(assetId);
        return asset ? referenceAssetLabel(asset, availableReferenceAssets.indexOf(asset)) : undefined;
      });
      const sourceAssetIds = (selectedReferenceAssets.length
        ? selectedReferenceAssets.map((asset) => asset.id)
        : [
          canvasNode.asset_id,
          ...upstreamNodes.filter((node) => node.kind === "image").map((node) => node.asset_id),
        ]).filter((assetId): assetId is string => Boolean(assetId));
      const uniqueSourceAssetIds = [...new Set(sourceAssetIds)];
      const referenceInstruction = selectedReferenceAssets.length ? `\n\n引用素材映射：\n${selectedReferenceAssets.map((asset, index) => (
        `- @${referenceAssetLabel(asset, index)}：输入图片 ${uniqueSourceAssetIds.indexOf(asset.id) + 1}，用于 ${asset.filename}。`
      )).join("\n")}\n参考图约束：用户明确引用的产品图是唯一产品依据。严格保持产品的形状、结构、材质、颜色、纹理、图案和身份特征；不得重新设计、替换或混入其他产品。若用户要求细节图、特写或局部图，只改变镜头距离与构图，展示该产品真实局部细节。` : "";
      const styleInstruction = operation.style && operation.style !== "自然" ? `\n\n画面风格：${operation.style}。` : "";
      const roleInstruction = operation.role_mode === "锁定人物" ? "\n\n人物要求：如画面中有人物，保持同一人物的身份与外观一致。" : "";
      const result = await generateCanvasImage(
        projectId,
        `${promptWithReferenceLabels}${referenceInstruction}${styleInstruction}${roleInstruction}`,
        operation.source_url?.trim() ?? "",
        uniqueSourceAssetIds,
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
      const mediaOutputCount = outputNodes.filter((node) => node.data.node.kind !== "text").length;
      const captionOutputCount = outputNodes.length - mediaOutputCount;
      const outputSummary = captionOutputCount
        ? `${mediaOutputCount} 个媒体节点和 ${captionOutputCount} 个作品文案节点`
        : `${mediaOutputCount} 个媒体节点`;
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
                detail: `提取完成，已生成 ${outputSummary}${warning}`.slice(0, 600),
                source_context: result.description.slice(0, 4_000),
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
    updateOperation(nodeId, { status: "running", error: "", message: "正在创建连续视频编辑片段…" });
    try {
      const result = await splitCanvasVideoByShots(projectId, assetId);
      const outputNodes = [toFlowNode({
        id: createCanvasNodeId(),
        kind: "shot_collection",
        x: source.position.x + 450,
        y: source.position.y - 36,
        title: `视频编辑片段组 · ${result.shots.length} 段`,
        detail: `整秒连续切分为 ${result.shots.length} 段；每段 4–8 秒，作为一次完整主体替换编辑任务`,
        content: source.data.node.content,
        source_context: source.data.node.source_context || source.data.node.content,
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
      commitVideoOutputs(nodeId, "shot", outputNodes, `已创建 ${result.shots.length} 个连续编辑片段，每段 4–8 秒，可直接执行完整主体替换`);
    } catch (error) {
      updateOperation(nodeId, {
        status: "failed",
        error: error instanceof Error ? error.message : "创建视频编辑片段失败",
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

  const composeVideoComparison = useCallback(async (nodeId: string) => {
    const target = nodes.find((node) => node.id === nodeId);
    if (!target || target.data.node.kind !== "video") return;
    const upstreamNodes = getUpstreamNodes(nodeId);
    const videoNodes = upstreamNodes
      .filter((node) => node.kind === "video" && node.asset_id)
      .sort((left, right) => left.y - right.y || left.x - right.x);
    const uniqueVideoNodes = [...new Map(videoNodes.map((node) => [node.asset_id!, node])).values()];
    if (uniqueVideoNodes.length < 2 || uniqueVideoNodes.length > 3) {
      updateOperation(nodeId, { status: "failed", error: "请连接 2～3 个不同的视频素材" });
      return;
    }
    if (videoAction) return;
    const audioNode = upstreamNodes.find((node) => node.kind === "audio" && node.asset_id)
      ?? upstreamNodes.find((node) => node.kind === "music" && node.asset_id);
    setVideoAction({ nodeId, type: "compare" });
    updateOperation(nodeId, {
      status: "running",
      error: "",
      message: `正在生成 ${uniqueVideoNodes.length} 路同步对比视频…`,
    });
    try {
      const result = await composeCanvasVideoComparison(
        projectId,
        uniqueVideoNodes.map((node) => node.asset_id!),
        audioNode?.asset_id,
      );
      const audioSource = upstreamNodes.find((node) => node.asset_id === result.audio_source_asset_id);
      const audioDetail = audioSource
        ? `音频来自“${audioSource.asset_name || audioSource.title}”`
        : "输入视频均无音轨，结果为静音";
      const message = `已生成 ${result.input_count} 路同步对比视频，${audioDetail}`;
      markDirty();
      setNodes((current) => current.map((node) => node.id === nodeId ? {
        ...node,
        data: { node: {
          ...node.data.node,
          title: result.asset.filename,
          detail: message,
          asset_id: result.asset.id,
          asset_url: result.asset.url,
          asset_name: result.asset.filename,
          operation: {
            ...(node.data.node.operation ?? initialOperation("video")),
            status: "succeeded" as const,
            error: "",
            message,
          },
        } },
      } : node));
    } catch (error) {
      updateOperation(nodeId, {
        status: "failed",
        error: error instanceof Error ? error.message : "对比视频生成失败",
      });
    } finally {
      setVideoAction(null);
    }
  }, [getUpstreamNodes, markDirty, nodes, projectId, setNodes, updateOperation, videoAction]);

  return {
    runNode,
    runExtractor,
    videoAction,
    splitVideoByShots,
    extractVideoKeyframes,
    composeVideoComparison,
  };
}
