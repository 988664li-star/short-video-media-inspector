from __future__ import annotations

from typing import Any

from backend.app.services.media import MediaRegistry, MediaResource


SESSION_PLACEHOLDER = "__MEDIA_SESSION__"


class MediaCatalog:
    """Collect and deduplicate upstream media while a payload is normalized."""

    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers
        self.resources: list[MediaResource] = []
        self._registered: dict[tuple[str, str], int] = {}

    def register(self, source_url: str, kind: str) -> int:
        key = (source_url, kind)
        if key not in self._registered:
            self.resources.append(MediaResource(source_url, self.headers, kind))
            self._registered[key] = len(self.resources) - 1
        return self._registered[key]

    def prepare(
        self,
        source_url: str | None,
        kind: str,
        label: str,
    ) -> dict[str, str] | None:
        if not source_url:
            return None
        index = self.register(source_url, kind)
        return {
            "label": label,
            "source_url": source_url,
            "proxy_url": f"/api/media/{SESSION_PLACEHOLDER}/{index}",
        }

    def commit(
        self, payload: dict[str, Any], registry: MediaRegistry
    ) -> dict[str, Any]:
        session_id = registry.add(self.resources)

        def finalize(item: Any) -> Any:
            if item is None:
                return None
            if isinstance(item, list):
                return [finalize(value) for value in item]
            if isinstance(item, dict):
                return {
                    key: finalize(value)
                    for key, value in item.items()
                    if value is not None
                }
            if isinstance(item, str):
                return item.replace(SESSION_PLACEHOLDER, session_id)
            return item

        return finalize(payload)
