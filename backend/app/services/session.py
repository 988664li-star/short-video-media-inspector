from __future__ import annotations

import threading
from typing import Any

from backend.app.core.config import settings


LOGIN_COOKIE_NAMES = {
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "sid_tt",
    "uid_tt",
    "uid_tt_ss",
}


def normalize_login_cookie(value: Any) -> tuple[str, list[str]]:
    """Validate a copied Request Headers Cookie value."""
    cookie = str(value or "").strip()
    if cookie.lower().startswith("set-cookie:"):
        raise ValueError("请粘贴 Request Headers 中的 Cookie 值，不要粘贴 Set-Cookie")
    if cookie.lower().startswith("cookie:"):
        cookie = cookie.split(":", 1)[1].strip()
    if not cookie:
        raise ValueError("请粘贴完整的抖音 Cookie")
    if len(cookie) > settings.max_cookie_size:
        raise ValueError("Cookie 内容过大")
    if any(character in cookie for character in ("\r", "\n", "\x00")):
        raise ValueError("Cookie 不能包含换行或控制字符")
    try:
        cookie.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Cookie 只能包含 ASCII 字符，请确认没有复制说明文字") from exc

    pairs: list[tuple[str, str]] = []
    for segment in cookie.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        if "=" not in segment:
            raise ValueError("Cookie 格式不正确，应为 name=value; name2=value2")
        name, item_value = segment.split("=", 1)
        name = name.strip()
        if not name or any(character.isspace() for character in name):
            raise ValueError("Cookie 中存在无效的字段名")
        pairs.append((name, item_value.strip()))
    if not pairs:
        raise ValueError("Cookie 中没有找到有效字段")
    return "; ".join(f"{name}={item_value}" for name, item_value in pairs) + ";", [
        name for name, _ in pairs
    ]


class LoginCookieStore:
    """Keep the active login Cookie in process memory only."""

    def __init__(self) -> None:
        self._cookie = ""
        self._names: list[str] = []
        self._lock = threading.Lock()

    def set(self, value: Any) -> dict[str, Any]:
        cookie, names = normalize_login_cookie(value)
        with self._lock:
            self._cookie = cookie
            self._names = names
        return self.status()

    def get(self) -> str:
        with self._lock:
            return self._cookie

    def clear(self) -> None:
        with self._lock:
            self._cookie = ""
            self._names = []

    def status(self) -> dict[str, Any]:
        with self._lock:
            names = list(self._names)
        return {
            "configured": bool(names),
            "cookie_count": len(names),
            "has_login_markers": bool(LOGIN_COOKIE_NAMES.intersection(names)),
        }
