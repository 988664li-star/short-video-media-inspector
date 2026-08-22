import type { CanvasReferenceAsset } from "../../types/canvas";

const INLINE_REFERENCE_PATTERN = /\[\[canvas-reference:([^\]]+)\]\]/g;

export type PromptReferenceSegment =
  | { type: "text"; value: string }
  | { type: "reference"; assetId: string; token: string };

function materialType(asset: CanvasReferenceAsset) {
  if (asset.mime_type.startsWith("image/")) return "图片";
  if (asset.mime_type.startsWith("video/")) return "视频";
  return "音频";
}

export function referenceAssetLabel(asset: CanvasReferenceAsset, index = 0) {
  return asset.label?.trim() || `${materialType(asset)}${index + 1}`;
}

export function normalizeReferenceAssets(assets: CanvasReferenceAsset[] | undefined) {
  return (assets ?? []).map((asset, index) => ({
    ...asset,
    label: referenceAssetLabel(asset, index),
  }));
}

export function nextReferenceAssetLabel(assets: CanvasReferenceAsset[] | undefined, mimeType: string) {
  const type = mimeType.startsWith("image/") ? "图片" : mimeType.startsWith("video/") ? "视频" : "音频";
  const count = (assets ?? []).filter((asset) => asset.mime_type.startsWith(`${mimeType.split("/", 1)[0]}/`)).length;
  return `${type}${count + 1}`;
}

/** An invisible-to-the-user token that keeps a reference asset at its typed position. */
export function inlineReferenceToken(assetId: string) {
  return `[[canvas-reference:${assetId}]]`;
}

export function splitPromptReferences(prompt: string): PromptReferenceSegment[] {
  const segments: PromptReferenceSegment[] = [];
  let cursor = 0;
  INLINE_REFERENCE_PATTERN.lastIndex = 0;

  for (const match of prompt.matchAll(INLINE_REFERENCE_PATTERN)) {
    const index = match.index ?? 0;
    if (index > cursor) segments.push({ type: "text", value: prompt.slice(cursor, index) });
    segments.push({ type: "reference", assetId: match[1], token: match[0] });
    cursor = index + match[0].length;
  }
  if (cursor < prompt.length || !segments.length || segments.at(-1)?.type === "reference") {
    segments.push({ type: "text", value: prompt.slice(cursor) });
  }
  return segments;
}

export function stripInlineReferences(prompt: string) {
  return prompt.replace(INLINE_REFERENCE_PATTERN, "");
}

export function removeInlineReference(prompt: string, assetId: string) {
  return prompt.replaceAll(inlineReferenceToken(assetId), "");
}

export function replaceInlineReferences(
  prompt: string,
  referenceLabel: (assetId: string) => string | undefined,
) {
  return prompt.replace(INLINE_REFERENCE_PATTERN, (token, assetId: string) => {
    const label = referenceLabel(assetId);
    return label ? `@${label}` : token;
  });
}
