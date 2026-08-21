import { GripVertical } from "lucide-react";
import { Handle, Position } from "@xyflow/react";
import type { ReactNode } from "react";

import type { CanvasNode } from "../../../types/canvas";

interface CanvasNodeShellProps {
  node: CanvasNode;
  selected: boolean;
  label: string;
  icon: ReactNode;
  children: ReactNode;
}

export function CanvasNodeShell({
  node,
  selected,
  label,
  icon,
  children,
}: CanvasNodeShellProps) {
  return (
    <article className={`canvas-node canvas-node--${node.kind}${selected ? " canvas-node--selected" : ""}`}>
      <Handle id="input" className="canvas-node__port canvas-node__port--input" type="target" position={Position.Left} />
      <header className="canvas-node__drag-handle">
        <span className="canvas-node__kind-icon" aria-hidden="true">{icon}</span>
        <span>{label}</span>
        <GripVertical className="canvas-node__grip" aria-hidden="true" />
      </header>
      {children}
      <Handle id="output" className="canvas-node__port canvas-node__port--output" type="source" position={Position.Right} />
    </article>
  );
}
