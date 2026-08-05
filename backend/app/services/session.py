from __future__ import annotations

import json
import os
from pathlib import Path
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
    """Thread-safe optional Cookie storage with an owner-only disk file."""

    def __init__(self, storage_path: Path | str | None = None) -> None:
        self._cookie = ""
        self._names: list[str] = []
        self._lock = threading.Lock()
        self._storage_path = Path(storage_path) if storage_path else None
        self._storage_error = ""
        self._restore()

    def _restore(self) -> None:
        if self._storage_path is None:
            return
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
            cookie, names = normalize_login_cookie(payload.get("cookie"))
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self._storage_error = "持久化 Cookie 文件无法读取，请重新保存或清除"
            return
        self._cookie = cookie
        self._names = names

    def _persist(self, cookie: str) -> None:
        if self._storage_path is None:
            return
        directory = self._storage_path.parent
        temporary_path = self._storage_path.with_suffix(
            f"{self._storage_path.suffix}.tmp"
        )
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(directory, 0o700)
            descriptor = os.open(
                temporary_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(
                    {"version": 1, "cookie": cookie},
                    file,
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self._storage_path)
            os.chmod(self._storage_path, 0o600)
        except OSError as exc:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError("Cookie 持久化保存失败，请检查后端数据目录权限") from exc

    def _remove_persisted(self) -> None:
        if self._storage_path is None:
            return
        try:
            self._storage_path.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError("持久化 Cookie 文件删除失败") from exc

    def set(self, value: Any) -> dict[str, Any]:
        cookie, names = normalize_login_cookie(value)
        with self._lock:
            self._persist(cookie)
            self._cookie = cookie
            self._names = names
            self._storage_error = ""
        return self.status()

    def get(self) -> str:
        with self._lock:
            return self._cookie

    def clear(self) -> None:
        with self._lock:
            self._remove_persisted()
            self._cookie = ""
            self._names = []
            self._storage_error = ""

    def status(self) -> dict[str, Any]:
        with self._lock:
            names = list(self._names)
            storage_error = self._storage_error
        return {
            "configured": bool(names),
            "cookie_count": len(names),
            "has_login_markers": bool(LOGIN_COOKIE_NAMES.intersection(names)),
            "storage": "backend_file" if self._storage_path else "memory",
            "storage_error": storage_error or None,
        }
