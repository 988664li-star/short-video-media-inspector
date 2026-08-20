"""Local vocal/accompaniment separation for speech transcription."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from backend.app.services.transcription.config import TranscriptionConfig
from backend.app.services.transcription.errors import VocalSeparationError


logger = logging.getLogger(__name__)


class VocalSeparator:
    """Extract the vocal stem with Demucs while retaining the source timing."""

    def __init__(self, config: TranscriptionConfig) -> None:
        self.config = config

    def extract_vocals(self, source_path: Path, output_path: Path) -> Path:
        if output_path.is_file() and output_path.stat().st_size > 0:
            return output_path
        output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix="f2-vocal-separation-") as temp_dir:
            command = [
                sys.executable,
                "-m",
                "demucs.separate",
                "--two-stems=vocals",
                "--name",
                self.config.vocal_separation_model,
                "--device",
                self.config.vocal_separation_device,
                "--mp3",
                "--out",
                temp_dir,
                str(source_path),
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self.config.vocal_separation_timeout_seconds,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                detail = getattr(exc, "stderr", "") or str(exc)
                raise VocalSeparationError(
                    f"人声/伴奏分离失败：{str(detail).strip()[-800:]}"
                ) from exc
            vocal_files = list(Path(temp_dir).glob("**/vocals.mp3"))
            if len(vocal_files) != 1 or vocal_files[0].stat().st_size == 0:
                raise VocalSeparationError("人声/伴奏分离没有生成有效的人声音轨")
            shutil.copy2(vocal_files[0], output_path)
            logger.info(
                "已分离人声音轨 [model=%s, device=%s, output=%s]",
                self.config.vocal_separation_model,
                self.config.vocal_separation_device,
                output_path,
            )
            return output_path
