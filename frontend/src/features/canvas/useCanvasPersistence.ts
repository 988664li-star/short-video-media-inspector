import { useCallback, useEffect, useRef, type Dispatch, type SetStateAction } from "react";

import type { CanvasDocument, CanvasViewport } from "../../types/canvas";
import {
  hasLegacyMaterialReferenceToken,
  mergeDuplicateReplacementTasks,
  toCanvasEdge,
  toCanvasNode,
} from "./canvasDocument";
import type { CanvasFlowEdge, CanvasFlowNode } from "./nodes/flowTypes";

interface UseCanvasPersistenceOptions {
  projectId: string;
  document: CanvasDocument;
  nodes: CanvasFlowNode[];
  edges: CanvasFlowEdge[];
  viewport: CanvasViewport;
  onDocumentChange: (document: CanvasDocument) => void;
  setNodes: Dispatch<SetStateAction<CanvasFlowNode[]>>;
  setEdges: Dispatch<SetStateAction<CanvasFlowEdge[]>>;
}

function serializedDocument(document: CanvasDocument) {
  return JSON.stringify({
    nodes: document.nodes,
    edges: document.edges ?? [],
    viewport: document.viewport,
  });
}

export function useCanvasPersistence({
  projectId,
  document,
  nodes,
  edges,
  viewport,
  onDocumentChange,
  setNodes,
  setEdges,
}: UseCanvasPersistenceOptions) {
  const saveTimer = useRef<number | null>(null);
  const documentChange = useRef(onDocumentChange);
  const dirty = useRef(false);
  const lastSavedDocument = useRef(serializedDocument(document));

  useEffect(() => {
    documentChange.current = onDocumentChange;
  }, [onDocumentChange]);

  useEffect(() => {
    if (!dirty.current) return;
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      dirty.current = false;
      saveTimer.current = null;
      const nextDocument = {
        nodes: nodes.map(toCanvasNode),
        edges: edges.map(toCanvasEdge),
        viewport,
      };
      const serialized = serializedDocument(nextDocument);
      if (serialized === lastSavedDocument.current) return;
      lastSavedDocument.current = serialized;
      documentChange.current(nextDocument);
    }, 320);
    return () => {
      if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    };
  }, [edges, nodes, viewport]);

  useEffect(() => {
    const merged = mergeDuplicateReplacementTasks(nodes, edges);
    if (!merged.changed) return;
    dirty.current = true;
    setNodes(merged.nodes);
    setEdges(merged.edges);
  }, [projectId]);

  useEffect(() => {
    if (!document.nodes.some(hasLegacyMaterialReferenceToken)) return;
    dirty.current = true;
    setNodes((current) => [...current]);
  }, [document.nodes, projectId, setNodes]);

  return useCallback(() => {
    dirty.current = true;
  }, []);
}
