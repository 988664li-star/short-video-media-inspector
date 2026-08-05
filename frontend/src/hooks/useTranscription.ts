import { useCallback, useRef, useState } from "react";

import { transcribeAweme } from "../api/douyin";
import type { InspectorData, TranscriptionData } from "../types/douyin";


const transcriptCache = new Map<string, TranscriptionData>();
const pendingTranscriptions = new Map<string, Promise<TranscriptionData>>();

export interface TranscriptionState {
  data: TranscriptionData | null;
  loading: boolean;
  error: string;
}

const EMPTY_STATE: TranscriptionState = {
  data: null,
  loading: false,
  error: "",
};

export function useTranscription() {
  const [state, setState] = useState<TranscriptionState>(EMPTY_STATE);
  const requestVersion = useRef(0);

  const start = useCallback((inspectorData: InspectorData) => {
    const version = requestVersion.current + 1;
    requestVersion.current = version;
    const { aweme_id: awemeId } = inspectorData;
    const mediaUrl = inspectorData.audio?.proxy_url ?? inspectorData.video?.proxy_url;
    const cached = transcriptCache.get(awemeId);

    if (cached) {
      setState({ data: cached, loading: false, error: "" });
      return;
    }
    if (!mediaUrl) {
      setState({ data: null, loading: false, error: "当前作品没有可供语音识别的音频或视频。" });
      return;
    }

    setState({ data: null, loading: true, error: "" });
    let pending = pendingTranscriptions.get(awemeId);
    if (!pending) {
      pending = transcribeAweme(awemeId, mediaUrl, inspectorData.description);
      pendingTranscriptions.set(awemeId, pending);
      void pending.then(
        () => pendingTranscriptions.delete(awemeId),
        () => pendingTranscriptions.delete(awemeId),
      );
    }

    void pending.then(
      (result) => {
        transcriptCache.set(awemeId, result);
        if (requestVersion.current === version) {
          setState({ data: result, loading: false, error: "" });
        }
      },
      (error: unknown) => {
        if (requestVersion.current === version) {
          setState({
            data: null,
            loading: false,
            error: error instanceof Error ? error.message : "文案生成失败，请稍后重试。",
          });
        }
      },
    );
  }, []);

  const clear = useCallback(() => {
    requestVersion.current += 1;
    setState(EMPTY_STATE);
  }, []);

  return { ...state, start, clear };
}
