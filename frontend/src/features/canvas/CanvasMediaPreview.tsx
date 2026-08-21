import { X } from "lucide-react";

import type { CanvasNode } from "../../types/canvas";

interface CanvasMediaPreviewProps {
  node: CanvasNode | null;
  onClose: () => void;
}

export function CanvasMediaPreview({ node, onClose }: CanvasMediaPreviewProps) {
  if (!node?.asset_url) return null;
  return (
    <div className="canvas-media-preview" role="presentation" onMouseDown={onClose}>
      <section className="canvas-media-preview__dialog" role="dialog" aria-modal="true" aria-label={node.title} onMouseDown={(event) => event.stopPropagation()}>
        <header><strong>{node.title}</strong><button type="button" onClick={onClose} aria-label="关闭预览"><X /></button></header>
        {node.kind === "image" ? <img src={node.asset_url} alt={node.title} /> : null}
        {node.kind === "video" ? <video src={node.asset_url} controls autoPlay playsInline /> : null}
        {node.kind === "music" || node.kind === "audio" ? <audio src={node.asset_url} controls autoPlay /> : null}
      </section>
    </div>
  );
}
