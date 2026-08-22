"""Private MinIO storage for Seedance test assets.

Only the configured dedicated bucket is ever addressed.  Objects stay private;
Seedance receives a short-lived presigned GET URL at submission time.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import PurePath
import re
from typing import BinaryIO
from urllib.parse import urlparse
from uuid import uuid4

from minio import Minio
from minio.error import S3Error

from backend.app.services.video_generation import VideoAssetPublisherError


class ObjectStorageError(VideoAssetPublisherError):
    pass


class SeedanceObjectStorage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        presign_seconds: int,
    ) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ObjectStorageError("SEEDANCE_OBJECT_STORAGE_ENDPOINT 必须是完整的 http(s) 地址")
        if not access_key or not secret_key:
            raise ObjectStorageError("未配置 MinIO 访问凭证")
        if not bucket:
            raise ObjectStorageError("未配置 Seedance 测试 bucket")
        self.bucket = bucket
        self.presign_seconds = max(60, min(presign_seconds, 7 * 24 * 60 * 60))
        self._client = Minio(
            parsed.netloc,
            access_key=access_key,
            secret_key=secret_key,
            secure=parsed.scheme == "https",
        )

    def ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
        except S3Error as exc:
            raise ObjectStorageError(f"Seedance 测试 bucket 不可用：{exc}") from exc

    def upload(
        self,
        analysis_id: str,
        file_handle: BinaryIO,
        size: int,
        filename: str,
        content_type: str,
    ) -> tuple[str, str]:
        self.ensure_bucket()
        suffix = PurePath(filename).suffix.lower()
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", PurePath(filename).stem).strip(".-") or "upload"
        object_key = f"seedance/{analysis_id}/{uuid4().hex}-{safe_name}{suffix}"
        try:
            self._client.put_object(
                self.bucket,
                object_key,
                file_handle,
                length=size,
                content_type=content_type,
            )
        except S3Error as exc:
            raise ObjectStorageError(f"上传 Seedance 测试素材失败：{exc}") from exc
        return f"minio-{uuid4().hex}", object_key

    def describe(self, object_key: str) -> tuple[int, str]:
        try:
            stat = self._client.stat_object(self.bucket, object_key)
            return int(stat.size), str(stat.content_type or "application/octet-stream")
        except S3Error as exc:
            raise ObjectStorageError(f"读取 Seedance 测试素材失败：{exc}") from exc

    def presign_download(self, object_key: str) -> str:
        try:
            return self._client.presigned_get_object(
                self.bucket,
                object_key,
                expires=timedelta(seconds=self.presign_seconds),
            )
        except S3Error as exc:
            raise ObjectStorageError(f"生成 Seedance 素材访问地址失败：{exc}") from exc
