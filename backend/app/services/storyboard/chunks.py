"""Bounded storyboard chunk planning and contact-sheet rendering."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any

from backend.app.core.config import Settings
from backend.app.services.replica_analysis.common import (
    ReplicaAnalysisNotReadyError,
    job_path as resolve_job_path,
    read_json,
    write_json,
)


@dataclass(frozen=True)
class StoryboardChunkConfig:
    data_path: Path
    ffmpeg_binary: str
    max_duration_seconds: float = 15.0
    forced_split_seconds: float = 14.0


class StoryboardChunkService:
    """Plan <=15-second chunks and render ordered keyframe contact sheets."""

    _manifest_version = 3

    def __init__(self, config: StoryboardChunkConfig) -> None:
        self.config = config
        self._job_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> "StoryboardChunkService":
        return cls(
            StoryboardChunkConfig(
                data_path=settings.shot_detection_data_path,
                ffmpeg_binary=settings.shot_detection_ffmpeg_binary,
            )
        )

    async def create(
        self, analysis_id: str, packages: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._job_lock:
            target = resolve_job_path(self.config.data_path, analysis_id)
            output_path = target / "storyboard_chunks" / "manifest.json"
            cached = read_json(output_path)
            if cached is not None and cached.get("manifest_version") == self._manifest_version:
                return {**cached, "cached": True}
            manifest = await asyncio.to_thread(
                self._create_sync, analysis_id, target, packages
            )
            await asyncio.to_thread(write_json, output_path, manifest)
            return {**manifest, "cached": False}

    def _create_sync(
        self,
        analysis_id: str,
        job_path: Path,
        packages: dict[str, Any],
    ) -> dict[str, Any]:
        source_scenes = self._normalized_scenes(packages)
        pieces = self._split_long_scenes(source_scenes)
        chunks = self._group_pieces(pieces)
        root = job_path / "storyboard_chunks"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        rendered_chunks = [
            self._render_chunk(job_path, root, chunk_id, chunk)
            for chunk_id, chunk in enumerate(chunks, start=1)
        ]
        return {
            "analysis_id": analysis_id,
            "manifest_version": self._manifest_version,
            "source_scene_packages": "scene_packages.json",
            "max_duration_seconds": self.config.max_duration_seconds,
            "forced_split_seconds": self.config.forced_split_seconds,
            "chunk_count": len(rendered_chunks),
            "chunks": rendered_chunks,
        }

    @staticmethod
    def _normalized_scenes(packages: dict[str, Any]) -> list[dict[str, Any]]:
        scenes: list[dict[str, Any]] = []
        for package in packages.get("scene_packages", []):
            if not isinstance(package, dict):
                continue
            start_ms = int(package.get("start_ms", 0))
            end_ms = int(package.get("end_ms", 0))
            scene_id = int(package.get("scene_id", 0))
            if scene_id <= 0 or end_ms <= start_ms:
                continue
            scenes.append(
                {
                    "scene_id": scene_id,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "frames": [
                        frame
                        for frame in package.get("frames", [])
                        if isinstance(frame, dict) and isinstance(frame.get("path"), str)
                    ],
                    "primary_transcript": list(package.get("primary_transcript", [])),
                    "context_transcript": list(package.get("context_transcript", [])),
                }
            )
        scenes.sort(key=lambda scene: (scene["start_ms"], scene["end_ms"], scene["scene_id"]))
        if not scenes:
            raise ReplicaAnalysisNotReadyError("没有可用于分段脚本的镜头，请重新执行自动分镜")
        return scenes

    def _split_long_scenes(self, scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Only split a source scene when that scene itself is longer than 15 seconds."""
        pieces: list[dict[str, Any]] = []
        max_duration_ms = round(self.config.max_duration_seconds * 1000)
        forced_duration_ms = round(self.config.forced_split_seconds * 1000)
        for scene in scenes:
            start_ms = scene["start_ms"]
            end_ms = scene["end_ms"]
            if end_ms - start_ms <= max_duration_ms:
                pieces.append({**scene, "forced_split": False})
                continue
            piece_start = start_ms
            while end_ms - piece_start > max_duration_ms:
                piece_end = piece_start + forced_duration_ms
                pieces.append(
                    {
                        **scene,
                        "start_ms": piece_start,
                        "end_ms": piece_end,
                        "forced_split": True,
                    }
                )
                piece_start = piece_end
            pieces.append(
                {
                    **scene,
                    "start_ms": piece_start,
                    "end_ms": end_ms,
                    "forced_split": True,
                }
            )
        return pieces

    def _group_pieces(self, pieces: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Greedily preserve shot boundaries while keeping every chunk at most 15 seconds."""
        chunks: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        chunk_start = 0
        max_duration_ms = round(self.config.max_duration_seconds * 1000)
        for piece in pieces:
            if not current:
                current = [piece]
                chunk_start = piece["start_ms"]
                continue
            if piece["end_ms"] - chunk_start <= max_duration_ms:
                current.append(piece)
                continue
            chunks.append(current)
            current = [piece]
            chunk_start = piece["start_ms"]
        if current:
            chunks.append(current)
        return chunks

    def _render_chunk(
        self,
        job_path: Path,
        root: Path,
        chunk_id: int,
        pieces: list[dict[str, Any]],
    ) -> dict[str, Any]:
        chunk_dir = root / f"segment_{chunk_id:03d}"
        chunk_dir.mkdir(exist_ok=True, mode=0o700)
        frame_dir = chunk_dir / "frames"
        frame_dir.mkdir(exist_ok=True, mode=0o700)
        rendered_pieces: list[dict[str, Any]] = []
        for order, piece in enumerate(pieces, start=1):
            selected = self._frames_for_piece(job_path, frame_dir, order, piece)
            rendered_pieces.append(
                {
                    "order": order,
                    "scene_id": piece["scene_id"],
                    "start_ms": piece["start_ms"],
                    "end_ms": piece["end_ms"],
                    "forced_split": piece["forced_split"],
                    "frame_paths": selected,
                    "primary_transcript": piece["primary_transcript"],
                    "context_transcript": piece["context_transcript"],
                    "original_dialogue": self._original_dialogue(piece),
                }
            )
        contact_sheet_path = chunk_dir / "storyboard.jpg"
        self._render_contact_sheet(job_path, contact_sheet_path, rendered_pieces)
        start_ms = rendered_pieces[0]["start_ms"]
        end_ms = rendered_pieces[-1]["end_ms"]
        return {
            "segment_id": chunk_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": end_ms - start_ms,
            "contact_sheet": contact_sheet_path.relative_to(job_path).as_posix(),
            "shots": rendered_pieces,
        }

    @staticmethod
    def _original_dialogue(piece: dict[str, Any]) -> str:
        primary = [str(item).strip() for item in piece["primary_transcript"] if str(item).strip()]
        context = [str(item).strip() for item in piece["context_transcript"] if str(item).strip()]
        return "；".join(dict.fromkeys(primary or context)) or "无"

    def _frames_for_piece(
        self,
        job_path: Path,
        frame_dir: Path,
        order: int,
        piece: dict[str, Any],
    ) -> list[str]:
        midpoint_ms = (piece["start_ms"] + piece["end_ms"]) // 2
        candidates = [
            frame
            for frame in piece["frames"]
            if piece["start_ms"] <= int(frame.get("timestamp_ms", -1)) <= piece["end_ms"]
        ]
        if candidates:
            return [
                str(frame["path"])
                for frame in sorted(
                    candidates,
                    key=lambda frame: (
                        int(frame["timestamp_ms"]),
                        abs(int(frame["timestamp_ms"]) - midpoint_ms),
                    ),
                )
            ]
        output_path = frame_dir / f"shot_{order:02d}.jpg"
        self._extract_frame(job_path / "source.mp4", output_path, midpoint_ms / 1000)
        return [output_path.relative_to(job_path).as_posix()]

    def _extract_frame(self, source_path: Path, output_path: Path, seconds: float) -> None:
        command = [
            self.config.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(source_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise ReplicaAnalysisNotReadyError("无法为强制切分的镜头导出关键帧") from exc

    @staticmethod
    def _render_contact_sheet(
        job_path: Path, output_path: Path, shots: list[dict[str, Any]]
    ) -> None:
        try:
            from PIL import Image, ImageDraw, ImageOps
        except ImportError as exc:
            raise ReplicaAnalysisNotReadyError("缺少 Pillow，无法生成拼接分镜图") from exc
        frames = [
            (shot, frame_index, frame_path)
            for shot in shots
            for frame_index, frame_path in enumerate(shot["frame_paths"], start=1)
        ]
        columns = min(4, max(1, len(frames)))
        image_width, image_height, label_height, gap = 216, 359, 28, 8
        rows = (len(frames) + columns - 1) // columns
        canvas = Image.new(
            "RGB",
            (
                gap + columns * (image_width + gap),
                gap + rows * (image_height + label_height + gap),
            ),
            "#10151e",
        )
        draw = ImageDraw.Draw(canvas)
        for index, (shot, frame_index, relative_frame_path) in enumerate(frames):
            frame_path = (job_path / relative_frame_path).resolve()
            try:
                frame_path.relative_to(job_path)
            except ValueError as exc:
                raise ReplicaAnalysisNotReadyError("分镜关键帧路径无效") from exc
            if not frame_path.is_file():
                raise ReplicaAnalysisNotReadyError("分镜关键帧不存在，请重新执行自动分镜")
            with Image.open(frame_path) as raw_image:
                image = ImageOps.contain(raw_image.convert("RGB"), (image_width, image_height))
            row, column = divmod(index, columns)
            x = gap + column * (image_width + gap)
            y = gap + row * (image_height + label_height + gap)
            canvas.paste(image, (x + (image_width - image.width) // 2, y))
            suffix = " *" if shot["forced_split"] else ""
            draw.text(
                (x, y + image_height + 7),
                f"S{shot['order']:02d}/F{frame_index} {shot['start_ms'] / 1000:.2f}-{shot['end_ms'] / 1000:.2f}{suffix}",
                fill="#e5eefb",
            )
        temporary_path = output_path.with_suffix(".partial")
        canvas.save(temporary_path, format="JPEG", quality=90, optimize=True)
        temporary_path.replace(output_path)
