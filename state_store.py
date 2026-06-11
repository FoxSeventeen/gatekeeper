"""SQLite-backed local trusted index for project bindings."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CREATED_BY, default_state_db_path


@dataclass
class ProjectBinding:
    project_id: str
    container_name: str
    image: str
    host_workspace: str
    config_path: str
    container_workspace: str
    logical_workspace: str
    state: str
    created_at: float
    updated_at: float
    last_used_at: float | None
    created_by: str = CREATED_BY


class StateStore:
    def __init__(self, db_path: Path | None = None, timeout: float = 10.0):
        self.db_path = db_path or default_state_db_path()
        self.timeout = timeout
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS project_bindings (
                    project_id TEXT PRIMARY KEY,
                    container_name TEXT NOT NULL,
                    image TEXT NOT NULL,
                    host_workspace TEXT NOT NULL,
                    config_path TEXT NOT NULL,
                    container_workspace TEXT NOT NULL,
                    logical_workspace TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_used_at REAL,
                    created_by TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_workspace_aliases (
                    session_id TEXT PRIMARY KEY,
                    root_session_id TEXT,
                    project_id TEXT NOT NULL,
                    seen_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tool_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT,
                    session_id TEXT,
                    tool_name TEXT NOT NULL,
                    args_json TEXT,
                    ok INTEGER,
                    returncode INTEGER,
                    stdout_preview TEXT,
                    stderr_preview TEXT,
                    duration_ms INTEGER,
                    created_at REAL NOT NULL
                );
                """
            )

    def get_project_binding(self, project_id: str) -> ProjectBinding | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM project_bindings WHERE project_id = ?", (project_id,)
            ).fetchone()
        return ProjectBinding(**dict(row)) if row else None

    def upsert_project_binding(self, binding: ProjectBinding) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO project_bindings (
                    project_id, container_name, image, host_workspace, config_path,
                    container_workspace, logical_workspace, state, created_at,
                    updated_at, last_used_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    container_name=excluded.container_name,
                    image=excluded.image,
                    host_workspace=excluded.host_workspace,
                    config_path=excluded.config_path,
                    container_workspace=excluded.container_workspace,
                    logical_workspace=excluded.logical_workspace,
                    state=excluded.state,
                    updated_at=excluded.updated_at,
                    last_used_at=excluded.last_used_at,
                    created_by=excluded.created_by
                """,
                (
                    binding.project_id,
                    binding.container_name,
                    binding.image,
                    binding.host_workspace,
                    binding.config_path,
                    binding.container_workspace,
                    binding.logical_workspace,
                    binding.state,
                    binding.created_at,
                    binding.updated_at,
                    binding.last_used_at,
                    binding.created_by,
                ),
            )

    def mark_project_state(self, project_id: str, state: str) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                "UPDATE project_bindings SET state = ?, updated_at = ? WHERE project_id = ?",
                (state, now, project_id),
            )

    def update_last_used_at(self, project_id: str) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                "UPDATE project_bindings SET last_used_at = ?, updated_at = ? WHERE project_id = ?",
                (now, now, project_id),
            )

    def upsert_session_alias(self, session_id: str, root_session_id: str | None, project_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO session_workspace_aliases (session_id, root_session_id, project_id, seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    root_session_id=excluded.root_session_id,
                    project_id=excluded.project_id,
                    seen_at=excluded.seen_at
                """,
                (session_id, root_session_id, project_id, time.time()),
            )

    def delete_session_alias(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM session_workspace_aliases WHERE session_id = ?", (session_id,))

    def get_project_id_for_session(self, session_id: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT project_id FROM session_workspace_aliases WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return str(row["project_id"]) if row else None

    def insert_tool_log(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        *,
        project_id: str | None = None,
        session_id: str | None = None,
        ok: bool | None = None,
        returncode: int | None = None,
        stdout: str = "",
        stderr: str = "",
        duration_ms: int | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tool_logs (
                    project_id, session_id, tool_name, args_json, ok, returncode,
                    stdout_preview, stderr_preview, duration_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    session_id,
                    tool_name,
                    json.dumps(args or {}, sort_keys=True),
                    None if ok is None else int(ok),
                    returncode,
                    stdout[:1000],
                    stderr[:1000],
                    duration_ms,
                    time.time(),
                ),
            )
