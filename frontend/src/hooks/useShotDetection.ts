import { useCallback, useRef, useState } from "react";

import { detectShots } from "../api/shotDetection";
import type { ShotDetectionResult } from "../types/shotDetection";

export function useShotDetection() {
  const [result, setResult] = useState<ShotDetectionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(0);

  const detect = useCallback(async (awemeId: string, mediaUrl: string) => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError("");
    try {
      const nextResult = await detectShots(awemeId, mediaUrl);
      if (requestId.current === currentRequest) setResult(nextResult);
    } catch (requestError) {
      if (requestId.current === currentRequest) {
        setError(requestError instanceof Error ? requestError.message : "自动分镜失败，请稍后重试。");
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
  }, []);

  return { result, loading, error, detect, reset };
}
