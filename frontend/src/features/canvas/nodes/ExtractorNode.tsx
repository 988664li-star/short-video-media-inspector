import { Download, Link2, LoaderCircle } from "lucide-react";
import type { NodeProps } from "@xyflow/react";

import { useCanvasNodeActions } from "./CanvasNodeActions";
import { CanvasNodeShell } from "./CanvasNodeShell";
import type { CanvasFlowNode } from "./flowTypes";

export function ExtractorNode({ id, data, selected }: NodeProps<CanvasFlowNode>) {
  const { runExtractor, updateText } = useCanvasNodeActions();
  const { node } = data;
  const status = node.operation?.status ?? "idle";
  const running = status === "running";

  return (
    <CanvasNodeShell node={node} selected={selected} label="链接提取" icon={<Link2 />}>
      <section className="canvas-extractor nodrag nowheel">
        <label htmlFor={`extractor-${id}`}>抖音 / TikTok 分享链接</label>
        <textarea
          id={`extractor-${id}`}
          value={node.content}
          rows={3}
          placeholder="粘贴分享文案或作品链接…"
          onKeyDown={(event) => event.stopPropagation()}
          onChange={(event) => updateText(id, event.target.value)}
        />
        <button
          type="button"
          disabled={running || !node.content.trim()}
          onClick={() => void runExtractor(id)}
        >
          {running ? <LoaderCircle className="canvas-extractor__spinner" /> : <Download />}
          {running ? "正在解析并保存…" : "提取返回的媒体"}
        </button>
        {node.operation?.error ? <p className="canvas-extractor__error" role="alert">{node.operation.error}</p> : null}
        {status === "succeeded" && node.detail ? <p className="canvas-extractor__success">{node.detail}</p> : null}
        <small>媒体会保存到当前画布，不依赖临时 CDN 地址。</small>
      </section>
    </CanvasNodeShell>
  );
}
