export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";


interface ApiErrorPayload {
  error?: string;
  detail?: string | Array<{ msg?: string }>;
}

const INTERNAL_ERROR_PATTERN = /(?:traceback|file\s+["'][^"']+["']\s*,?\s*line\s+\d+|\/(?:home|users|var|tmp|opt|srv)\/|[a-z]:\\|localhost|127\.0\.0\.1|sqlite|(?:authorization|api[_ -]?key|bearer|cookie|token)\s*[:=]|https?:\/\/\S+(?:token|signature|x-signature)=)/i;

export const publicErrorMessage = (message: unknown, fallback: string): string => {
  if (typeof message !== "string") return fallback;
  const normalized = message.trim();
  if (!normalized || normalized.length > 240 || INTERNAL_ERROR_PATTERN.test(normalized)) return fallback;
  return normalized;
};

const errorMessage = (payload: ApiErrorPayload, fallback: string): string => {
  if (typeof payload.detail === "string") return publicErrorMessage(payload.detail, fallback);
  if (Array.isArray(payload.detail)) {
    return publicErrorMessage(payload.detail.map((item) => item.msg).filter(Boolean).join("；"), fallback);
  }
  return publicErrorMessage(payload.error, fallback);
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
