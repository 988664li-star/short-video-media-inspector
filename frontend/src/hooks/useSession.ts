import { useCallback, useEffect, useState } from "react";

import {
  clearSessionCookie,
  getSessionStatus,
  saveSessionCookie,
} from "../api/douyin";
import type { SessionStatus } from "../types/douyin";


const VISITOR_STATUS: SessionStatus = {
  configured: false,
  cookie_count: 0,
  has_login_markers: false,
};

let sessionStatusRequest: Promise<SessionStatus> | null = null;

function loadSessionStatus() {
  if (!sessionStatusRequest) {
    sessionStatusRequest = getSessionStatus().catch((error) => {
      sessionStatusRequest = null;
      throw error;
    });
  }
  return sessionStatusRequest;
}

export function useSession(onCleared: () => void) {
  const [status, setStatus] = useState<SessionStatus>(VISITOR_STATUS);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [tone, setTone] = useState<"default" | "success" | "error">("default");

  useEffect(() => {
    let active = true;
    loadSessionStatus()
      .then((nextStatus) => {
        if (active) setStatus(nextStatus);
      })
      .catch(() => {
        if (active) {
          setMessage("暂时无法读取 Cookie 状态。");
          setTone("error");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const save = useCallback(async (cookie: string) => {
    setBusy(true);
    setMessage("正在载入 Cookie…");
    setTone("default");
    try {
      const nextStatus = await saveSessionCookie(cookie);
      sessionStatusRequest = Promise.resolve(nextStatus);
      setStatus(nextStatus);
      setRevision((value) => value + 1);
      setMessage(nextStatus.message || "Cookie 已载入，仅在当前服务运行期间有效");
      setTone(nextStatus.has_login_markers ? "success" : "default");
      return true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Cookie 载入失败。");
      setTone("error");
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  const clear = useCallback(async () => {
    setBusy(true);
    try {
      const nextStatus = await clearSessionCookie();
      sessionStatusRequest = Promise.resolve(nextStatus);
      setStatus(nextStatus);
      setRevision((value) => value + 1);
      setMessage(nextStatus.message || "登录 Cookie 已清除");
      setTone("success");
      onCleared();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Cookie 清除失败。");
      setTone("error");
    } finally {
      setBusy(false);
    }
  }, [onCleared]);

  return { status, revision, busy, message, tone, save, clear };
}

export type SessionController = ReturnType<typeof useSession>;
