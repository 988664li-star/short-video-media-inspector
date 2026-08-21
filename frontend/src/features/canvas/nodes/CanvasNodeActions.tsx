import { createContext, type ReactNode, useContext } from "react";

import type {
  CanvasNode,
  CanvasNodeOperation,
  CanvasReplacementTask,
} from "../../../types/canvas";

export type VideoNodeAction = "split" | "keyframes";

interface CanvasNodeActionsValue {
  updateText: (nodeId: string, content: string) => void;
  updateOperation: (nodeId: string, patch: Partial<CanvasNodeOperation>) => void;
  saveNodeInstruction: (nodeId: string) => void;
  uploadNodeAsset: (nodeId: string, kind: "image" | "video", file: File) => Promise<void>;
  uploadReferenceAsset: (nodeId: string, file: File) => Promise<void>;
  uploadingNodeId: string | null;
  splitVideoByShots: (nodeId: string) => Promise<void>;
  extractVideoKeyframes: (nodeId: string) => Promise<void>;
  videoAction: { nodeId: string; type: VideoNodeAction } | null;
  analyzeReplaceables: (nodeId: string) => Promise<void>;
  replacementAnalysisNodeId: string | null;
  createReplacementTask: (analysisNodeId: string, objectId: string) => void;
  updateReplacementTask: (nodeId: string, patch: Partial<CanvasReplacementTask>) => void;
  updateReplacementShotPrompt: (nodeId: string, shotIndex: number, prompt: string) => void;
  buildReplacementPrompts: (nodeId: string) => void;
  runNode: (nodeId: string) => Promise<void>;
  runExtractor: (nodeId: string) => Promise<void>;
  getUpstreamNodes: (nodeId: string) => CanvasNode[];
  previewMedia: (node: CanvasNode) => void;
}

const CanvasNodeActionsContext = createContext<CanvasNodeActionsValue | null>(null);

export function CanvasNodeActionsProvider({
  children,
  value,
}: {
  children: ReactNode;
  value: CanvasNodeActionsValue;
}) {
  return <CanvasNodeActionsContext.Provider value={value}>{children}</CanvasNodeActionsContext.Provider>;
}

export function useCanvasNodeActions() {
  const actions = useContext(CanvasNodeActionsContext);
  if (!actions) throw new Error("Canvas node actions are unavailable");
  return actions;
}
