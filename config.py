"""Configuration defaults for the project-centric Docker runtime plugin."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PLUGIN_NAME = "docker-runtime"
CREATED_BY = "hermes-docker-runtime-plugin"
DEFAULT_IMAGE = "hermes-docker-runtime:latest"
DEFAULT_PROBE_IMAGE = "alpine:latest"
CONTAINER_WORKSPACE = "/workspace"
PROJECT_CONFIG_RELATIVE = Path(".hermes") / "docker-runtime.json"


def hermes_home() -> Path:
    return Path(os.getenv("HERMES_HOME", Path.home() / ".hermes")).expanduser()


def default_state_db_path() -> Path:
    return hermes_home() / "plugins" / "docker_runtime" / "state.db"


@dataclass(frozen=True)
class DockerRuntimeSettings:
    image: str = DEFAULT_IMAGE
    probe_image: str = DEFAULT_PROBE_IMAGE
    state_db_path: Path = field(default_factory=default_state_db_path)
    container_workspace: str = CONTAINER_WORKSPACE
    logical_workspace: str = CONTAINER_WORKSPACE
    docker_bin: str = "docker"
    allowed_roots: tuple[Path, ...] = ()
    deny_roots: tuple[Path, ...] = (
        Path("/"),
        Path("/etc"),
        Path("/root"),
        Path("/usr"),
        Path("/var"),
        Path("/bin"),
        Path("/sbin"),
        Path("/proc"),
        Path("/sys"),
        Path("/dev"),
    )
    network: str = "none"
    command_timeout_seconds: int = 120
    docker_probe_timeout_seconds: int = 20
    docker_probe_enabled: bool = True


DEFAULT_SETTINGS = DockerRuntimeSettings()
