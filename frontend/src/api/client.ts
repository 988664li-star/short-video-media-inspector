export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";


interface ApiErrorPayload {
  error?: string;
  detail?: string | Array<{ msg?: string }>;
}

const errorMessage = (payload: ApiErrorPayload, fallback: string): string => {
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail.map((item) => item.msg).filter(Boolean).join("；") || fallback;
  }
  return payload.error || fallback;
};

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  fallback = "请求失败",
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  const payload = (await response.json()) as T & ApiErrorPayload;
  if (!response.ok) throw new Error(errorMessage(payload, fallback));
  return payload;
}
