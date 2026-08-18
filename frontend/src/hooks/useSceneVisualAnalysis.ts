import { useCallback, useRef, useState } from "react";

import { streamSceneAnalysis } from "../api/shotDetection";
import type { SceneVisualAnalysisResult } from "../types/shotDetection";

export function useSceneVisualAnalysis() {
  const [result, setResult] = useState<SceneVisualAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [progressMessage, setProgressMessage] = useState("");
  const requestId = useRef(0);

  const analyze = useCallback(async (analysisId: string, context: string, force = false) => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError("");
    setProgressMessage("正在准备镜头视觉分析");
    setResult(null);
    try {
      await streamSceneAnalysis(analysisId, context, force, (event) => {
        if (requestId.current !== currentRequest) return;
        if (event.type === "progress") {
          setProgressMessage(event.message);
          return;
        }
        if (event.type === "scene") {
          setProgressMessage(`已完成 ${event.completed}/${event.total} 个镜头的视觉分析`);
          setResult((current) => ({
            analysis_id: analysisId,
            model: current?.model ?? "",
            cached: false,
            scene_analyses: [...(current?.scene_analyses ?? []).filter((item) => item.scene_id !== event.analysis.scene_id), event.analysis],
          }));
          return;
        }
        setProgressMessage("镜头视觉分析已完成");
        setResult(event.result);
      });
    } catch (requestError) {
      if (requestId.current === currentRequest) {
        setError(requestError instanceof Error ? requestError.message : "镜头视觉分析失败，请稍后重试。");
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

  return { result, loading, error, progressMessage, analyze, reset };
}
