import { useCallback, useRef, useState } from "react";

import { buildReplicaPlaybook } from "../api/shotDetection";
import type { ReplicaPlaybookResult } from "../types/shotDetection";

export function useReplicaPlaybook() {
  const [result, setResult] = useState<ReplicaPlaybookResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requestId = useRef(0);

  const build = useCallback(async (analysisId: string) => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError("");
    try {
      const nextResult = await buildReplicaPlaybook(analysisId);
      if (requestId.current === currentRequest) setResult(nextResult);
    } catch (requestError) {
      if (requestId.current === currentRequest) {
        setError(requestError instanceof Error ? requestError.message : "生成复刻方案失败，请稍后重试。");
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

  const restore = useCallback((savedResult: ReplicaPlaybookResult | null) => {
    requestId.current += 1;
    setResult(savedResult);
    setLoading(false);
    setError("");
  }, []);

  return { result, loading, error, build, restore, reset };
}
