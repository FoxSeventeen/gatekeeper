"""Project-local `.hermes/docker-runtime.json` handling."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import (
    CONTAINER_WORKSPACE,
    CREATED_BY,
    DEFAULT_IMAGE,
    PROJECT_CONFIG_RELATIVE,
)
from .errors import ProjectConfigError

PROJECT_ID_RE = re.compile(r"^proj_[a-f0-9]{12,32}$")
CONTAINER_NAME_RE = re.compile(r"^hermes-runtime-[a-f0-9][a-f0-9_.-]{5,60}$")


@dataclass
class ProjectConfig:
    schema_version: int
    project_id: str
    container_name: str
    image: str
    container_workspace: str
    logical_workspace: str
    created_at: str
    updated_at: str
    created_by: str
    binding_mode: str
    host_workspace_hint: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectConfig":
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def config_path_for_workspace(host_workspace: Path) -> Path:
    return host_workspace / PROJECT_CONFIG_RELATIVE


def generate_project_id() -> str:
    return f"proj_{uuid.uuid4().hex[:12]}"


def container_name_for_project(project_id: str) -> str:
    suffix = project_id.removeprefix("proj_")[:12]
    return f"hermes-runtime-{suffix}"


def validate_project_config(config: ProjectConfig) -> None:
    if config.schema_version != 1:
        raise ProjectConfigError("Unsupported project config schema_version")
    if not PROJECT_ID_RE.match(config.project_id):
        raise ProjectConfigError("Invalid project_id in project config")
    if not CONTAINER_NAME_RE.match(config.container_name):
        raise ProjectConfigError("Invalid container_name in project config")
    if config.container_workspace != CONTAINER_WORKSPACE:
        raise ProjectConfigError("container_workspace must be /workspace")
    if config.logical_workspace != CONTAINER_WORKSPACE:
        raise ProjectConfigError("logical_workspace must be /workspace")
    if config.created_by != CREATED_BY:
        raise ProjectConfigError("created_by is not this plugin")
    if config.binding_mode != "workspace_config":
        raise ProjectConfigError("binding_mode must be workspace_config")


def read_project_config(host_workspace: Path) -> ProjectConfig | None:
    path = config_path_for_workspace(host_workspace)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        config = ProjectConfig.from_dict(data)
        validate_project_config(config)
        return config
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise ProjectConfigError(f"Unable to read project config: {exc}") from exc


def create_project_config(host_workspace: Path, image: str = DEFAULT_IMAGE) -> ProjectConfig:
    now = utc_now_iso()
    project_id = generate_project_id()
    config = ProjectConfig(
        schema_version=1,
        project_id=project_id,
        container_name=container_name_for_project(project_id),
        image=image,
        container_workspace=CONTAINER_WORKSPACE,
        logical_workspace=CONTAINER_WORKSPACE,
        created_at=now,
        updated_at=now,
        created_by=CREATED_BY,
        binding_mode="workspace_config",
        host_workspace_hint=str(host_workspace),
    )
    validate_project_config(config)
    return config


def write_project_config(host_workspace: Path, config: ProjectConfig) -> None:
    validate_project_config(config)
    path = config_path_for_workspace(host_workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".docker-runtime.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
