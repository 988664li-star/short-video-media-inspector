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
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { CanvasNode, CanvasReferenceAsset, CanvasVideoModel } from "../../../types/canvas";
import {
  inlineReferenceToken,
  removeInlineReference,
  splitPromptReferences,
  referenceAssetLabel,
} from "../referenceAssets";
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
  return { id: node.asset_id, url: node.asset_url, filename: node.asset_name, mime_type: mimeType, label: node.title };
}

function materialIcon(asset: CanvasReferenceAsset) {
  if (asset.mime_type.startsWith("image/")) return <Image aria-hidden="true" />;
  if (asset.mime_type.startsWith("video/")) return <Video aria-hidden="true" />;
  return <Type aria-hidden="true" />;
}

function modelOptions(node: CanvasNode, videoModels: CanvasVideoModel[]) {
  if (node.kind === "image") return [{ value: "doubao-seedream-5-0-260128", label: "Seedream 5.0" }];
  if (node.kind === "text") return [{ value: "Qwen/Qwen3.6-27B", label: "Qwen 3.6" }];
  if (node.kind === "video") return videoModels
    .filter((model) => model.capabilities.includes("video_edit"))
    .map((model) => ({ value: model.id, label: model.label }));
  return [{ value: "", label: "跟随节点" }];
}

function serializePromptNodes(nodes: NodeListOf<ChildNode> | ChildNode[]): string {
  return Array.from(nodes).map((node) => {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
    if (!(node instanceof HTMLElement)) return "";
    if (node.dataset.referenceToken) return node.dataset.referenceToken;
    if (node.dataset.promptPlaceholder !== undefined) return "";
    return serializePromptNodes(node.childNodes);
  }).join("").replaceAll("\u200B", "");
}

function createReferenceToken(
  asset: CanvasReferenceAsset,
  token: string,
  label: string,
  onRemove: (asset: CanvasReferenceAsset) => void,
) {
  const attachment = document.createElement("span");
  attachment.className = "canvas-ai-composer__inline-attachment";
  attachment.contentEditable = "false";
  attachment.dataset.referenceToken = token;
  attachment.title = `引用素材：@${label} · ${asset.filename}`;
  if (asset.mime_type.startsWith("image/")) {
    const image = document.createElement("img");
    image.src = asset.url;
    image.alt = asset.filename;
    attachment.append(image);
  } else {
    attachment.textContent = asset.mime_type.startsWith("video/") ? "视频" : "音频";
  }
  const remove = document.createElement("button");
  remove.type = "button";
  remove.setAttribute("aria-label", `移除引用：@${label}`);
  remove.textContent = "×";
  remove.addEventListener("mousedown", (event) => event.preventDefault());
  remove.addEventListener("click", () => onRemove(asset));
  attachment.append(remove);
  return attachment;
}

function renderPromptEditor(
  editor: HTMLDivElement,
  prompt: string,
  materialsById: Map<string, CanvasReferenceAsset>,
  availableMaterials: CanvasReferenceAsset[],
  onRemove: (asset: CanvasReferenceAsset) => void,
) {
  const content = document.createDocumentFragment();
  for (const segment of splitPromptReferences(prompt)) {
    if (segment.type === "text") {
      content.append(document.createTextNode(segment.value));
      continue;
    }
    const asset = materialsById.get(segment.assetId);
    if (!asset) continue;
    const label = referenceAssetLabel(asset, availableMaterials.indexOf(asset));
    content.append(createReferenceToken(asset, segment.token, label, onRemove));
  }
  editor.replaceChildren(content);
}

function focusAfterReference(editor: HTMLDivElement, token: string, occurrenceIndex: number) {
  try {
    const reference = Array.from(editor.querySelectorAll<HTMLElement>("[data-reference-token]"))
      .filter((element) => element.dataset.referenceToken === token)[occurrenceIndex];
    const trailingText = reference?.nextSibling;
    if (!trailingText || trailingText.nodeType !== Node.TEXT_NODE) return;
    const range = document.createRange();
    range.setStart(trailingText, Math.min(1, trailingText.textContent?.length ?? 0));
    range.collapse(true);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    editor.focus();
  } catch {
    editor.focus();
  }
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
    videoModels,
  } = useCanvasNodeActions();
  const operation = node.operation;
  const running = operation?.status === "running";
  const [mentionOpen, setMentionOpen] = useState(false);
  const [urlOpen, setUrlOpen] = useState(Boolean(operation?.source_url));
  const uploadInput = useRef<HTMLInputElement>(null);
  const promptEditor = useRef<HTMLDivElement>(null);
  const promptCaretOffset = useRef<number | null>(null);
  const promptDraft = useRef(operation?.prompt ?? "");
  const promptReferenceIds = useRef(operation?.referenced_asset_ids ?? []);
  const lastEmittedPrompt = useRef(operation?.prompt ?? "");
  const migratedLegacyNodeIds = useRef(new Set<string>());
  const [draftHasContent, setDraftHasContent] = useState(Boolean(operation?.prompt));
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
  const materialsById = useMemo(() => new Map(availableMaterials.map((asset) => [asset.id, asset])), [availableMaterials]);
  const models = modelOptions(node, videoModels);
  const selectedModel = operation?.model || models[0]?.value || "";
  const selectedModelIsAvailable = models.some((model) => model.value === selectedModel);

  useEffect(() => {
    if (migratedLegacyNodeIds.current.has(nodeId)) return;
    migratedLegacyNodeIds.current.add(nodeId);
    const prompt = operation?.prompt ?? "";
    const promptWithoutReferenceTriggers = prompt.replace(/@(?=\[\[canvas-reference:)/g, "");
    const referencedIds = new Set(
      splitPromptReferences(promptWithoutReferenceTriggers)
        .filter((segment) => segment.type === "reference")
        .map((segment) => segment.assetId),
    );
    const missingLegacyReferences = selectedMaterials
      .filter((asset) => !referencedIds.has(asset.id))
      .map((asset) => inlineReferenceToken(asset.id))
      .join("");
    const migratedPrompt = `${promptWithoutReferenceTriggers}${missingLegacyReferences}`;
    if (migratedPrompt === prompt) return;
    promptDraft.current = migratedPrompt;
    promptReferenceIds.current = selectedIds;
    setDraftHasContent(true);
    updateOperation(nodeId, { prompt: migratedPrompt });
  }, [nodeId, operation?.prompt, selectedIds, selectedMaterials, updateOperation]);

  const syncPromptDraft = useCallback((prompt: string) => {
    promptDraft.current = prompt;
    lastEmittedPrompt.current = prompt;
    promptReferenceIds.current = [...new Set(splitPromptReferences(prompt).flatMap((segment) => (
      segment.type === "reference" && materialsById.has(segment.assetId) ? [segment.assetId] : []
    )))];
    setDraftHasContent(Boolean(prompt));
    setMentionOpen(prompt.endsWith("@"));
  }, [materialsById]);

  const commitPromptDraft = useCallback(() => {
    const prompt = promptDraft.current;
    if (prompt === (operation?.prompt ?? "")
      && promptReferenceIds.current.join("\0") === (operation?.referenced_asset_ids ?? []).join("\0")) return;
    updateOperation(nodeId, {
      prompt,
      referenced_asset_ids: promptReferenceIds.current,
      status: "idle",
      error: "",
      message: "",
    });
  }, [nodeId, operation?.prompt, operation?.referenced_asset_ids, updateOperation]);

  const removeMaterialReference = useCallback((asset: CanvasReferenceAsset) => {
    const editor = promptEditor.current;
    if (editor) Array.from(editor.querySelectorAll<HTMLElement>("[data-reference-token]")).forEach((element) => {
      if (element.dataset.referenceToken === inlineReferenceToken(asset.id)) element.remove();
    });
    syncPromptDraft(editor ? serializePromptNodes(editor.childNodes) : removeInlineReference(promptDraft.current, asset.id));
  }, [syncPromptDraft]);

  useEffect(() => {
    const editor = promptEditor.current;
    const prompt = operation?.prompt ?? "";
    if (!editor || document.activeElement === editor) return;
    promptDraft.current = prompt;
    promptReferenceIds.current = operation?.referenced_asset_ids ?? [];
    setDraftHasContent(Boolean(prompt));
    renderPromptEditor(editor, prompt, materialsById, availableMaterials, removeMaterialReference);
    lastEmittedPrompt.current = prompt;
  }, [availableMaterials, materialsById, operation?.prompt, operation?.referenced_asset_ids, removeMaterialReference]);

  const rememberPromptCaret = () => {
    try {
      const editor = promptEditor.current;
      const selection = window.getSelection();
      if (!editor || !selection?.rangeCount) return;
      const range = selection.getRangeAt(0);
      if (!editor.contains(range.startContainer)) return;
      const beforeCaret = range.cloneRange();
      beforeCaret.selectNodeContents(editor);
      beforeCaret.setEnd(range.startContainer, range.startOffset);
      promptCaretOffset.current = serializePromptNodes(beforeCaret.cloneContents().childNodes).length;
    } catch {
      promptCaretOffset.current = null;
    }
  };

  const addMaterialReference = (asset: CanvasReferenceAsset) => {
    const currentPrompt = promptDraft.current;
    let insertionOffset = Math.min(promptCaretOffset.current ?? currentPrompt.length, currentPrompt.length);
    let promptWithoutTrigger = currentPrompt;
    if (currentPrompt[insertionOffset - 1] === "@") {
      promptWithoutTrigger = `${currentPrompt.slice(0, insertionOffset - 1)}${currentPrompt.slice(insertionOffset)}`;
      insertionOffset -= 1;
    }
    const editor = promptEditor.current;
    const token = inlineReferenceToken(asset.id);
    const prefix = promptWithoutTrigger.slice(0, insertionOffset);
    const occurrenceIndex = splitPromptReferences(prefix)
      .filter((segment) => segment.type === "reference" && segment.assetId === asset.id)
      .length;
    const prompt = `${prefix}${token} ${promptWithoutTrigger.slice(insertionOffset)}`;
    if (editor) {
      renderPromptEditor(editor, prompt, materialsById, availableMaterials, removeMaterialReference);
      focusAfterReference(editor, token, occurrenceIndex);
    }
    promptCaretOffset.current = insertionOffset + token.length + 1;
    syncPromptDraft(prompt);
    setMentionOpen(false);
  };

  const runWithPromptDraft = () => {
    commitPromptDraft();
    void runNode(nodeId, {
      prompt: promptDraft.current,
      referenced_asset_ids: promptReferenceIds.current,
    });
  };

  return (
    <section
      className="canvas-ai-composer nodrag nopan nowheel"
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
        <div
          ref={promptEditor}
          className="canvas-ai-composer__prompt-editor"
          contentEditable
          suppressContentEditableWarning
          role="textbox"
          aria-multiline="true"
          aria-label="图片生成提示词"
          onKeyDown={(event) => event.stopPropagation()}
          onKeyUp={rememberPromptCaret}
          onMouseUp={rememberPromptCaret}
          onFocus={rememberPromptCaret}
          onInput={(event) => {
            const prompt = serializePromptNodes(event.currentTarget.childNodes);
            rememberPromptCaret();
            syncPromptDraft(prompt);
          }}
          onBlur={commitPromptDraft}
        />
        {!draftHasContent ? <span className="canvas-ai-composer__prompt-placeholder">{promptPlaceholder}</span> : null}
        {mentionOpen ? (
          <div className="canvas-ai-composer__mention-menu" role="listbox" aria-label="引用素材">
            {availableMaterials.length ? availableMaterials.map((asset, index) => (
              <button key={asset.id} type="button" role="option" onMouseDown={(event) => event.preventDefault()} onClick={() => addMaterialReference(asset)}>
                {asset.mime_type.startsWith("image/") ? <img src={asset.url} alt="" /> : materialIcon(asset)}
                <span><strong>@{referenceAssetLabel(asset, index)}</strong><small>{asset.filename}</small></span>
              </button>
            )) : <p>先通过左下角「素材」上传图片、视频或音频。</p>}
          </div>
        ) : null}
      </div>

      <footer className="canvas-ai-composer__tools">
        <button type="button" title="上传图片、视频或音频到当前节点的素材库" disabled={uploadingNodeId === nodeId} onClick={() => uploadInput.current?.click()}>
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
        <button type="button" title="查看并引用已上传或上游素材" onClick={() => setMentionOpen((open) => !open)}><AtSign /><span>引用</span></button>
        {allowSourceUrl ? <button type="button" title="添加参考图片网址" onClick={() => setUrlOpen((open) => !open)}><Link /><span>链接</span></button> : null}
        <label title="画面风格"><Palette /><select aria-label="画面风格" value={operation?.style ?? "自然"} onChange={(event) => updateOperation(nodeId, { style: event.target.value })}><option value="自然">自然</option><option value="电影感">电影感</option><option value="商品广告">商品广告</option></select></label>
        <label title="生成模型"><Bot /><select aria-label="生成模型" disabled={!models.length} value={selectedModel} onChange={(event) => updateOperation(nodeId, { model: event.target.value })}>{selectedModel && !selectedModelIsAvailable ? <option value={selectedModel}>{selectedModel}</option> : null}{models.map((model) => <option key={model.value} value={model.value}>{model.label}</option>)}{!models.length ? <option value="">没有可用模型</option> : null}</select></label>
        {(node.kind === "image" || node.kind === "video") ? <>
          <label title="画面比例"><select aria-label="画面比例" value={operation?.aspect_ratio ?? "原比例"} onChange={(event) => updateOperation(nodeId, { aspect_ratio: event.target.value })}><option value="原比例">原比例</option><option value="9:16">9:16</option><option value="16:9">16:9</option><option value="1:1">1:1</option></select></label>
          <label title="生成清晰度"><select aria-label="生成清晰度" value={operation?.quality ?? "1K"} onChange={(event) => updateOperation(nodeId, { quality: event.target.value })}><option value="1K">1K</option><option value="2K">2K</option></select></label>
          <label title="角色设计模式"><select aria-label="角色设计模式" value={operation?.role_mode ?? "通用"} onChange={(event) => updateOperation(nodeId, { role_mode: event.target.value })}><option value="通用">通用</option><option value="锁定人物">锁定人物</option></select></label>
        </> : null}
        <button className="canvas-ai-composer__submit" type="button" title={actionLabel} disabled={running} onClick={() => isInstruction ? saveNodeInstruction(nodeId) : runWithPromptDraft()}>
          {running ? <LoaderCircle className="spin" /> : isInstruction ? <Save /> : <SendHorizontal />}
          <span>{running ? "处理中" : actionLabel}</span>
        </button>
      </footer>
      {operation?.status === "failed" && operation.error ? <p className="canvas-ai-composer__message canvas-ai-composer__message--error" role="alert">{operation.error}</p> : null}
      {operation?.status === "succeeded" ? <p className="canvas-ai-composer__message canvas-ai-composer__message--success">{operation.message || (isInstruction ? "处理指令已保存" : "生成完成，结果已回填")}</p> : null}
    </section>
  );
}
