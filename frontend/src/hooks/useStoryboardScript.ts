import { useCallback, useRef, useState } from "react";

import { streamStoryboardScript } from "../api/shotDetection";
import type { StoryboardScriptResult } from "../types/shotDetection";

export function useStoryboardScript() {
  const [result, setResult] = useState<StoryboardScriptResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [progressMessage, setProgressMessage] = useState("");
  const requestId = useRef(0);

  const build = useCallback(async (analysisId: string, context: string, force = false) => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError("");
    setProgressMessage("正在准备分段分镜图");
    setResult(null);
    try {
      await streamStoryboardScript(analysisId, context, force, (event) => {
        if (requestId.current !== currentRequest) return;
        if (event.type === "progress") {
          setProgressMessage(event.message);
          return;
        }
        if (event.type === "segment") {
          setProgressMessage(`已完成 ${event.completed}/${event.total} 个 15 秒分段`);
          setResult((current) => ({
            analysis_id: analysisId,
            model: current?.model ?? "",
            cached: false,
            segments: [
              ...(current?.segments ?? []).filter((item) => item.segment_id !== event.segment.segment_id),
              event.segment,
            ].sort((left, right) => left.segment_id - right.segment_id),
          }));
          return;
        }
        setProgressMessage("分段分镜脚本已完成");
        setResult(event.result);
      });
    } catch (requestError) {
      if (requestId.current === currentRequest) {
        setError(requestError instanceof Error ? requestError.message : "生成分段分镜脚本失败，请稍后重试。");
      }
    } finally {
      if (requestId.current === currentRequest) setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    requestId.current += 1;
    setResult(null);
    setLoading(false);
    setError("");
    setProgressMessage("");
  }, []);

  const restore = useCallback((savedResult: StoryboardScriptResult | null) => {
    requestId.current += 1;
    setResult(savedResult);
    setLoading(false);
    setError("");
    setProgressMessage(savedResult ? "已恢复已保存的分段分镜脚本" : "");
  }, []);

  return { result, loading, error, progressMessage, build, restore, reset };
}
