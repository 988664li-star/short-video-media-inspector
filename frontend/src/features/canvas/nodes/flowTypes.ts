import type { Edge, Node } from "@xyflow/react";

import type { CanvasNode, CanvasNodeKind } from "../../../types/canvas";

export type CanvasFlowNodeData = { node: CanvasNode };
export type CanvasFlowNode = Node<CanvasFlowNodeData, CanvasNodeKind>;
export type CanvasFlowEdge = Edge;
