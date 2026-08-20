"""Persistent project configuration for the viral-replication workflow."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import time
from typing import Any
from uuid import uuid4


class ReplicaProjectService:
    """Save the operator's reusable product, brand and rights configuration."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS replica_projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    market TEXT NOT NULL,
                    audience TEXT NOT NULL,
                    landing_page TEXT NOT NULL DEFAULT '',
                    target_cpa REAL,
                    brand_facts TEXT NOT NULL DEFAULT '',
                    prohibited_claims TEXT NOT NULL DEFAULT '',
                    rights_mode TEXT NOT NULL,
                    rights_confirmed INTEGER NOT NULL,
                    aigc_label_required INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS replica_projects_updated_at
                    ON replica_projects (updated_at DESC);
                """
            )

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM replica_projects ORDER BY updated_at DESC"
            ).fetchall()
        return [self._payload(row) for row in rows]

    def save_project(self, payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
        now = int(time.time() * 1000)
        project_id = project_id or uuid4().hex
        values = (
            payload["name"],
            payload["product_name"],
            payload["platform"],
            payload["market"],
            payload["audience"],
            payload.get("landing_page", ""),
            payload.get("target_cpa"),
            payload.get("brand_facts", ""),
            payload.get("prohibited_claims", ""),
            payload["rights_mode"],
            int(bool(payload["rights_confirmed"])),
            int(bool(payload["aigc_label_required"])),
            now,
        )
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM replica_projects WHERE id = ?", (project_id,)
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO replica_projects (
                        id, name, product_name, platform, market, audience,
                        landing_page, target_cpa, brand_facts, prohibited_claims,
                        rights_mode, rights_confirmed, aigc_label_required, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (project_id, *values, now),
                )
            else:
                connection.execute(
                    """
                    UPDATE replica_projects SET
                        name = ?, product_name = ?, platform = ?, market = ?, audience = ?,
                        landing_page = ?, target_cpa = ?, brand_facts = ?, prohibited_claims = ?,
                        rights_mode = ?, rights_confirmed = ?, aigc_label_required = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, project_id),
                )
            row = connection.execute(
                "SELECT * FROM replica_projects WHERE id = ?", (project_id,)
            ).fetchone()
        return self._payload(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "product_name": row["product_name"],
            "platform": row["platform"],
            "market": row["market"],
            "audience": row["audience"],
            "landing_page": row["landing_page"],
            "target_cpa": row["target_cpa"],
            "brand_facts": row["brand_facts"],
            "prohibited_claims": row["prohibited_claims"],
            "rights_mode": row["rights_mode"],
            "rights_confirmed": bool(row["rights_confirmed"]),
            "aigc_label_required": bool(row["aigc_label_required"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
