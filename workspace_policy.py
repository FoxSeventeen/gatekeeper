"""Policy checks for user-supplied host workspace paths."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

from .config import DEFAULT_SETTINGS, DockerRuntimeSettings
from .errors import WorkspacePolicyError


class WorkspaceDockerProbeError(WorkspacePolicyError):
    """Raised when Docker daemon cannot bind-mount the requested workspace."""


def _normalize_absolute_host_path(raw_path: str | Path) -> str:
    text = str(raw_path).strip()
    if not text:
        raise WorkspacePolicyError("workspace path is empty")
    if not text.startswith("/"):
        raise WorkspacePolicyError(f"workspace path must be an absolute host path: {text}")

    path = PurePosixPath(text)
    if ".." in path.parts:
        raise WorkspacePolicyError(f"workspace path must not contain '..': {text}")
    return str(path)


def _is_same_or_child(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def validate_workspace_path_syntax(
    raw_path: str | Path,
    settings: DockerRuntimeSettings = DEFAULT_SETTINGS,
) -> str:
    normalized = _normalize_absolute_host_path(raw_path)

    deny_roots = tuple(str(PurePosixPath(str(root))) for root in settings.deny_roots)
    if normalized in deny_roots:
        raise WorkspacePolicyError(f"workspace path is a denied system directory: {normalized}")

    allowed_roots = tuple(str(PurePosixPath(str(root))) for root in settings.allowed_roots)
    if allowed_roots and not any(_is_same_or_child(normalized, root) for root in allowed_roots):
        raise WorkspacePolicyError(f"workspace path is outside allowed roots: {normalized}")

    return normalized


def validate_workspace_visible_to_docker(host_path: str, *, settings: DockerRuntimeSettings = DEFAULT_SETTINGS) -> None:
    cmd = [
        settings.docker_bin,
        "run",
        "--rm",
        "--mount",
        f"type=bind,source={host_path},target=/workspace,readonly",
        settings.probe_image,
        "sh",
        "-lc",
        "test -d /workspace && ls -la /workspace >/dev/null",
    ]

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=settings.docker_probe_timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise WorkspaceDockerProbeError(
            "docker command not found. Gatekeeper needs Docker CLI or Docker socket access."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise WorkspaceDockerProbeError(f"Docker workspace probe timed out for path: {host_path}") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise WorkspaceDockerProbeError(
            "workspace path is not visible to Docker daemon or cannot be mounted: "
            f"{host_path}. returncode={proc.returncode}, stderr={stderr!r}, stdout={stdout!r}"
        )


def validate_host_workspace(
    raw_path: str | Path,
    settings: DockerRuntimeSettings = DEFAULT_SETTINGS,
) -> Path:
    normalized = validate_workspace_path_syntax(raw_path, settings)
    if settings.docker_probe_enabled:
        validate_workspace_visible_to_docker(normalized, settings=settings)
    return Path(normalized)
