import {
  AtSign,
  Bot,
  Image,
  Link,
  LoaderCircle,
  Palette,
  Plus,
  Save,
  SendHorizontal,
  Type,
  Video,
  X,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import type { CanvasNode, CanvasReferenceAsset } from "../../../types/canvas";
import { useCanvasNodeActions } from "./CanvasNodeActions";

interface CanvasNodeComposerProps {
  nodeId: string;
  node: CanvasNode;
  actionLabel: string;
  promptPlaceholder: string;
  allowSourceUrl?: boolean;
  mode?: "generate" | "instruction";
  assistantTitle?: string;
  assistantDescription?: string;
}

function materialFromNode(node: CanvasNode): CanvasReferenceAsset | null {
  if (!node.asset_id || !node.asset_url || !node.asset_name) return null;
  const mimeType = node.kind === "image" ? "image/*" : node.kind === "video" ? "video/*" : "audio/*";
  return { id: node.asset_id, url: node.asset_url, filename: node.asset_name, mime_type: mimeType };
}

function materialIcon(asset: CanvasReferenceAsset) {
  if (asset.mime_type.startsWith("image/")) return <Image aria-hidden="true" />;
  if (asset.mime_type.startsWith("video/")) return <Video aria-hidden="true" />;
  return <Type aria-hidden="true" />;
}

function modelOptions(node: CanvasNode) {
  if (node.kind === "image") return [{ value: "doubao-seedream-5-0-260128", label: "Seedream 5.0" }];
  if (node.kind === "text") return [{ value: "Qwen/Qwen3.6-27B", label: "Qwen 3.6" }];
  if (node.kind === "video") return [{ value: "doubao-seedance-2-0-mini-260615", label: "Seedance 2.0" }];
  return [{ value: "", label: "跟随节点" }];
}

export function CanvasNodeComposer({
  nodeId,
  node,
  actionLabel,
  promptPlaceholder,
  allowSourceUrl = false,
  mode = "generate",
  assistantTitle,
  assistantDescription,
}: CanvasNodeComposerProps) {
  const {
    getUpstreamNodes,
    runNode,
    saveNodeInstruction,
    updateOperation,
    uploadReferenceAsset,
    uploadingNodeId,
  } = useCanvasNodeActions();
  const operation = node.operation;
  const running = operation?.status === "running";
  const [mentionOpen, setMentionOpen] = useState(false);
  const [urlOpen, setUrlOpen] = useState(Boolean(operation?.source_url));
  const uploadInput = useRef<HTMLInputElement>(null);
  const upstreamNodes = getUpstreamNodes(nodeId);
  const isInstruction = mode === "instruction";
  const title = assistantTitle ?? (node.kind === "text" ? "AI 文本助手" : "AI 图片助手");
  const description = assistantDescription ?? "结果会回填到当前节点";
  const availableMaterials = useMemo(() => {
    const materials = [
      ...(node.reference_assets ?? []),
      ...upstreamNodes.flatMap((upstreamNode) => [
        ...(upstreamNode.reference_assets ?? []),
        materialFromNode(upstreamNode),
      ]),
    ].filter((asset): asset is CanvasReferenceAsset => Boolean(asset));
    return [...new Map(materials.map((asset) => [asset.id, asset])).values()];
  }, [node.reference_assets, upstreamNodes]);
  const selectedIds = operation?.referenced_asset_ids ?? [];
  const selectedMaterials = availableMaterials.filter((asset) => selectedIds.includes(asset.id));
  const models = modelOptions(node);

  const updatePrompt = (prompt: string) => {
    updateOperation(nodeId, { prompt, status: "idle", error: "", message: "" });
    if (prompt.endsWith("@")) setMentionOpen(true);
  };

  const addMaterialReference = (asset: CanvasReferenceAsset) => {
    if (selectedIds.includes(asset.id)) {
      setMentionOpen(false);
      return;
    }
    const mention = `@${asset.filename}`;
    updateOperation(nodeId, {
      referenced_asset_ids: [...selectedIds, asset.id],
      prompt: `${operation?.prompt ?? ""}${operation?.prompt?.trim() ? " " : ""}${mention}`,
      status: "idle",
      error: "",
      message: "",
    });
    setMentionOpen(false);
  };

  const removeMaterialReference = (asset: CanvasReferenceAsset) => {
    updateOperation(nodeId, {
      referenced_asset_ids: selectedIds.filter((id) => id !== asset.id),
      status: "idle",
      error: "",
      message: "",
    });
  };

  return (
    <section
      className="canvas-ai-composer nodrag nowheel"
      aria-label={`${actionLabel}操作区`}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <header className="canvas-ai-composer__meta">
        <strong>{title}</strong>
        <span title={description}>{description}</span>
        {node.asset_name ? <span className="canvas-ai-composer__current" title="当前节点的主素材">当前：{node.asset_name}</span> : null}
        {selectedMaterials.length ? <span className="canvas-ai-composer__current">已引用 {selectedMaterials.length} 项素材</span> : null}
      </header>

      {allowSourceUrl && urlOpen ? (
        <label className="canvas-ai-composer__url">
          <Link aria-hidden="true" />
          <input
            value={operation?.source_url ?? ""}
            type="url"
            inputMode="url"
            placeholder="粘贴参考图片网址…"
            onKeyDown={(event) => event.stopPropagation()}
            onChange={(event) => updateOperation(nodeId, { source_url: event.target.value, status: "idle", error: "" })}
          />
        </label>
      ) : null}

      <div className="canvas-ai-composer__workspace">
        {selectedMaterials.length ? (
          <div className="canvas-ai-composer__attachments" aria-label="已引用素材">
            {selectedMaterials.map((asset) => (
              <button
                className="canvas-ai-composer__attachment"
                key={asset.id}
                type="button"
                title={`移除引用：${asset.filename}`}
                onClick={() => removeMaterialReference(asset)}
              >
                {asset.mime_type.startsWith("image/") ? <img src={asset.url} alt={asset.filename} /> : materialIcon(asset)}
                <X aria-hidden="true" />
              </button>
            ))}
          </div>
        ) : null}
        <textarea
          value={operation?.prompt ?? ""}
          rows={4}
          placeholder={promptPlaceholder}
          onKeyDown={(event) => event.stopPropagation()}
          onChange={(event) => updatePrompt(event.target.value)}
        />
        {mentionOpen ? (
          <div className="canvas-ai-composer__mention-menu" role="listbox" aria-label="引用素材">
            {availableMaterials.length ? availableMaterials.map((asset) => (
              <button key={asset.id} type="button" role="option" onClick={() => addMaterialReference(asset)}>
                {asset.mime_type.startsWith("image/") ? <img src={asset.url} alt="" /> : materialIcon(asset)}
                <span>{asset.filename}</span>
              </button>
            )) : <p>先通过左下角「素材」上传图片、视频或音频。</p>}
          </div>
        ) : null}
      </div>

      <footer className="canvas-ai-composer__tools">
        <button type="button" title="上传图片、视频或音频素材" disabled={uploadingNodeId === nodeId} onClick={() => uploadInput.current?.click()}>
          {uploadingNodeId === nodeId ? <LoaderCircle className="spin" /> : <Plus />}<span>素材</span>
        </button>
        <input
          ref={uploadInput}
          type="file"
          accept="image/*,video/*,audio/*"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.currentTarget.value = "";
            if (file) void uploadReferenceAsset(nodeId, file);
          }}
        />
        <button type="button" title="使用 @ 引用已上传或上游素材" onClick={() => setMentionOpen((open) => !open)}><AtSign /><span>引用</span></button>
        {allowSourceUrl ? <button type="button" title="添加参考图片网址" onClick={() => setUrlOpen((open) => !open)}><Link /><span>链接</span></button> : null}
        <label title="画面风格"><Palette /><select aria-label="画面风格" value={operation?.style ?? "自然"} onChange={(event) => updateOperation(nodeId, { style: event.target.value })}><option value="自然">自然</option><option value="电影感">电影感</option><option value="商品广告">商品广告</option></select></label>
        <label title="生成模型"><Bot /><select aria-label="生成模型" value={operation?.model ?? models[0].value} onChange={(event) => updateOperation(nodeId, { model: event.target.value })}>{models.map((model) => <option key={model.value} value={model.value}>{model.label}</option>)}</select></label>
        {(node.kind === "image" || node.kind === "video") ? <>
          <label title="画面比例"><select aria-label="画面比例" value={operation?.aspect_ratio ?? "原比例"} onChange={(event) => updateOperation(nodeId, { aspect_ratio: event.target.value })}><option value="原比例">原比例</option><option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option></select></label>
          <label title="生成清晰度"><select aria-label="生成清晰度" value={operation?.quality ?? "1K"} onChange={(event) => updateOperation(nodeId, { quality: event.target.value })}><option value="1K">1K</option><option value="2K">2K</option></select></label>
          <label title="角色设计模式"><select aria-label="角色设计模式" value={operation?.role_mode ?? "通用"} onChange={(event) => updateOperation(nodeId, { role_mode: event.target.value })}><option value="通用">通用</option><option value="锁定人物">锁定人物</option></select></label>
        </> : null}
        <button className="canvas-ai-composer__submit" type="button" title={actionLabel} disabled={running} onClick={() => isInstruction ? saveNodeInstruction(nodeId) : void runNode(nodeId)}>
          {running ? <LoaderCircle className="spin" /> : isInstruction ? <Save /> : <SendHorizontal />}
          <span>{running ? "处理中" : actionLabel}</span>
        </button>
      </footer>
      {operation?.status === "failed" && operation.error ? <p className="canvas-ai-composer__message canvas-ai-composer__message--error" role="alert">{operation.error}</p> : null}
      {operation?.status === "succeeded" ? <p className="canvas-ai-composer__message canvas-ai-composer__message--success">{operation.message || (isInstruction ? "处理指令已保存" : "生成完成，结果已回填")}</p> : null}
    </section>
  );
}
