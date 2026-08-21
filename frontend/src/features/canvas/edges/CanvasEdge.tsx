import { BaseEdge, getBezierPath, type EdgeProps } from "@xyflow/react";

import type { CanvasFlowEdge } from "../nodes/flowTypes";

export function CanvasEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  selected,
}: EdgeProps<CanvasFlowEdge>) {
  const [path] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    curvature: 0.34,
  });
  const gradientId = `canvas-edge-gradient-${id}`;

  return (
    <g className={`canvas-edge${selected ? " canvas-edge--selected" : ""}`}>
      <defs>
        <linearGradient id={gradientId} gradientUnits="userSpaceOnUse" x1={sourceX} y1={sourceY} x2={targetX} y2={targetY}>
          <stop offset="0%" stopColor={selected ? "#ff727c" : "#5c9fe0"} />
          <stop offset="100%" stopColor={selected ? "#ffb16d" : "#66d0b1"} />
        </linearGradient>
      </defs>
      <path className="canvas-edge__glow" d={path} />
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        interactionWidth={28}
        className="canvas-edge__main"
        style={{ stroke: `url(#${gradientId})` }}
      />
      <path className="canvas-edge__motion" d={path} />
    </g>
  );
}
