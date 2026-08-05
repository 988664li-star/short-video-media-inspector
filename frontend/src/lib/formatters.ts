import type { Nullable } from "../types/douyin";


export const hasValue = (value: unknown): boolean => {
  if (value === null || value === undefined || value === "" || value === "—") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
};

export const formatDuration = (milliseconds: Nullable<number>): string => {
  if (!Number.isFinite(Number(milliseconds))) return "—";
  const totalSeconds = Math.round(Number(milliseconds) / 1000);
  return `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(totalSeconds % 60).padStart(2, "0")}`;
};

export const formatCount = (value: Nullable<number>): string => {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
};

export const formatBytes = (value: Nullable<number>): string => {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
};

export const displayValue = (value: unknown): string => {
  if (value === true) return "是";
  if (value === false) return "否";
  if (Array.isArray(value)) return value.join("、");
  if (typeof value === "object" && value !== null) return JSON.stringify(value, null, 2);
  return String(value ?? "—");
};

export const awemeTypeLabel = (value: unknown): string => {
  const labels: Record<number, string> = {
    0: "普通视频",
    4: "普通视频",
    55: "横屏视频",
    61: "竖屏视频",
    68: "图集作品",
    109: "日常作品",
    201: "短剧/合集视频",
  };
  return labels[Number(value)] ?? displayValue(value);
};
