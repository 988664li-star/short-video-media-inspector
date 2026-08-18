import { useCallback, useState } from "react";

import { resolveAweme } from "../api/douyin";
import type { ContentPlatform } from "../api/douyin";
import type { InspectorData } from "../types/douyin";
import { useTranscription } from "./useTranscription";


export const DEFAULT_SHARE_TEXT = "2.56 eBG:/ J@V.lP :0pm 03/23 6月29日素材突出展示 有粉丝问，口播里有素材需要突出展示，需要怎么排版？素材怎么高亮显示？今天一个视频讲清楚。# 视频剪辑# 素材 # 口播 # 剪辑教程  https://v.douyin.com/ABsTdyaUZLA/ 复制此链接，打开Dou音搜索，直接观看视频！";

export interface ResolveOptions {
  shareText?: string;
  awemeId?: string;
  scrollToResult?: boolean;
}

export function useInspector() {
  const [shareText, setShareText] = useState(DEFAULT_SHARE_TEXT);
  const [platform, setPlatform] = useState<ContentPlatform>("auto");
  const [data, setData] = useState<InspectorData | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"default" | "success" | "error">("default");
  const transcription = useTranscription();

  const resolve = useCallback(async (options: ResolveOptions = {}) => {
    const requestedText = (options.shareText ?? shareText).trim();
    if (!requestedText) {
      setMessage("请先粘贴抖音分享内容。");
      setMessageTone("error");
      return false;
    }
    setLoading(true);
    setMessage(options.awemeId
      ? `正在切换到作品 ${options.awemeId}，并获取完整信息…`
      : "正在获取作品详情、评论、相关推荐和作者作品…");
    setMessageTone("default");
    try {
      const result = await resolveAweme(requestedText, options.awemeId, options.awemeId ? "douyin" : platform);
      setData(result);
      transcription.clear();
      setShareText(requestedText);
      const warning = result.warnings?.[0];
      setMessage(warning || `解析成功 · 作品 ${result.aweme_id} · ${result.access_mode === "login_cookie" ? "登录 Cookie 模式" : "游客模式"}`);
      setMessageTone(warning ? "default" : "success");
      if (options.scrollToResult) {
        requestAnimationFrame(() => document.querySelector("#result")?.scrollIntoView({ behavior: "smooth", block: "start" }));
      }
      return true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "解析失败，请稍后重试。");
      setMessageTone("error");
      return false;
    } finally {
      setLoading(false);
    }
  }, [shareText, transcription.start]);

  const clear = useCallback((nextMessage = "") => {
    setData(null);
    transcription.clear();
    setMessage(nextMessage);
    setMessageTone(nextMessage ? "success" : "default");
  }, [transcription.clear]);

  const resetInput = useCallback(() => {
    setShareText("");
    clear();
  }, [clear]);

  const extractTranscription = useCallback(() => {
    if (data) {
      transcription.start(data);
    }
  }, [data, transcription.start]);

  return {
    shareText,
    setShareText,
    platform,
    setPlatform,
    data,
    loading,
    message,
    messageTone,
    resolve,
    extractTranscription,
    clear,
    resetInput,
    transcription: {
      data: transcription.data,
      loading: transcription.loading,
      error: transcription.error,
    },
  };
}

export type InspectorController = ReturnType<typeof useInspector>;
