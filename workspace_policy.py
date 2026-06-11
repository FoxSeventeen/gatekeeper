"""Policy checks for user-supplied host workspace paths."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path, PurePosixPath

from .config import DEFAULT_SETTINGS, DockerRuntimeSettings
from .errors import WorkspacePolicyError


logger = logging.getLogger(__name__)


class WorkspaceDockerProbeError(WorkspacePolicyError):
    """Raised when Docker daemon cannot bind-mount the requested workspace."""


def _normalize_absolute_host_path(raw_path: str | Path) -> str:
    text = str(raw_path).strip()
    logger.info("Gatekeeper 工作区路径校验：收到原始路径 raw_path=%r，去除首尾空白后 text=%r", raw_path, text)
    if not text:
        logger.info("Gatekeeper 工作区路径校验失败：路径为空")
        raise WorkspacePolicyError("workspace path is empty")
    if not text.startswith("/"):
        logger.info("Gatekeeper 工作区路径校验失败：路径不是绝对宿主机路径 path=%s", text)
        raise WorkspacePolicyError(f"workspace path must be an absolute host path: {text}")

    path = PurePosixPath(text)
    if ".." in path.parts:
        logger.info("Gatekeeper 工作区路径校验失败：路径包含 '..' path=%s parts=%s", text, path.parts)
        raise WorkspacePolicyError(f"workspace path must not contain '..': {text}")
    logger.info("Gatekeeper 工作区路径校验：纯字符串规范化结果 normalized=%s parts=%s", str(path), path.parts)
    return str(path)


def _is_same_or_child(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def validate_workspace_path_syntax(
    raw_path: str | Path,
    settings: DockerRuntimeSettings = DEFAULT_SETTINGS,
) -> str:
    normalized = _normalize_absolute_host_path(raw_path)

    deny_roots = tuple(str(PurePosixPath(str(root))) for root in settings.deny_roots)
    logger.info("Gatekeeper 工作区路径策略：normalized=%s deny_roots=%s", normalized, deny_roots)
    if normalized in deny_roots:
        logger.info("Gatekeeper 工作区路径策略拒绝：命中 deny_roots normalized=%s", normalized)
        raise WorkspacePolicyError(f"workspace path is a denied system directory: {normalized}")

    allowed_roots = tuple(str(PurePosixPath(str(root))) for root in settings.allowed_roots)
    logger.info("Gatekeeper 工作区路径策略：normalized=%s allowed_roots=%s", normalized, allowed_roots)
    if allowed_roots and not any(_is_same_or_child(normalized, root) for root in allowed_roots):
        logger.info("Gatekeeper 工作区路径策略拒绝：不在 allowed_roots 范围内 normalized=%s", normalized)
        raise WorkspacePolicyError(f"workspace path is outside allowed roots: {normalized}")

    logger.info("Gatekeeper 工作区路径策略通过：normalized=%s", normalized)
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
    logger.info(
        "Gatekeeper Docker 可见性探测开始：host_path=%s docker_bin=%s probe_image=%s timeout=%s cmd=%r",
        host_path,
        settings.docker_bin,
        settings.probe_image,
        settings.docker_probe_timeout_seconds,
        cmd,
    )

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=settings.docker_probe_timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        logger.info("Gatekeeper Docker 可见性探测失败：找不到 docker 命令 docker_bin=%s", settings.docker_bin)
        raise WorkspaceDockerProbeError(
            "docker command not found. Gatekeeper needs Docker CLI or Docker socket access."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        logger.info("Gatekeeper Docker 可见性探测失败：超时 host_path=%s timeout=%s", host_path, settings.docker_probe_timeout_seconds)
        raise WorkspaceDockerProbeError(f"Docker workspace probe timed out for path: {host_path}") from exc

    logger.info(
        "Gatekeeper Docker 可见性探测结束：host_path=%s returncode=%s stdout=%r stderr=%r",
        host_path,
        proc.returncode,
        (proc.stdout or "").strip(),
        (proc.stderr or "").strip(),
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        logger.info(
            "Gatekeeper Docker 可见性探测失败：Docker daemon 无法挂载路径 host_path=%s returncode=%s stderr=%r stdout=%r",
            host_path,
            proc.returncode,
            stderr,
            stdout,
        )
        raise WorkspaceDockerProbeError(
            "workspace path is not visible to Docker daemon or cannot be mounted: "
            f"{host_path}. returncode={proc.returncode}, stderr={stderr!r}, stdout={stdout!r}"
        )
    logger.info("Gatekeeper Docker 可见性探测通过：Docker daemon 可以挂载 host_path=%s", host_path)


def validate_host_workspace(
    raw_path: str | Path,
    settings: DockerRuntimeSettings = DEFAULT_SETTINGS,
) -> Path:
    logger.info("Gatekeeper 工作区校验开始：raw_path=%r docker_probe_enabled=%s", raw_path, settings.docker_probe_enabled)
    normalized = validate_workspace_path_syntax(raw_path, settings)
    local_path = Path(normalized)
    logger.info(
        "Gatekeeper 本地进程视角诊断：normalized=%s local_exists=%s local_is_dir=%s。注意：这里只用于日志诊断，不作为宿主机路径判断依据。",
        normalized,
        local_path.exists(),
        local_path.is_dir(),
    )
    if settings.docker_probe_enabled:
        validate_workspace_visible_to_docker(normalized, settings=settings)
    else:
        logger.info("Gatekeeper Docker 可见性探测已关闭：跳过 host_path=%s", normalized)
    logger.info("Gatekeeper 工作区校验完成：host_workspace=%s", normalized)
    return Path(normalized)
