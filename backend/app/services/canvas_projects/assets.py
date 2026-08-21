"""Local-file storage for canvas image and video assets."""

from __future__ import annotations

from pathlib import Path
import re


class CanvasAssetStorage:
    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path

    def write(self, project_id: str, asset_id: str, filename: str, content: bytes) -> str:
        extension = Path(filename).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", extension):
            extension = ""
        stored_filename = f"{asset_id}{extension}"
        asset_path = self._asset_directory(project_id) / stored_filename
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = asset_path.with_suffix(f"{asset_path.suffix}.partial")
        temporary.write_bytes(content)
        temporary.replace(asset_path)
        return stored_filename

    def path_for(self, project_id: str, stored_filename: str) -> Path:
        candidate = (self._asset_directory(project_id) / stored_filename).resolve()
        root = self._asset_directory(project_id).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return root / ".missing"
        return candidate

    def _asset_directory(self, project_id: str) -> Path:
        return self.data_path / project_id / "assets"
