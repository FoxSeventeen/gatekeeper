"""Policy checks for user-supplied host workspace paths."""

from __future__ import annotations

from pathlib import Path

from .config import DEFAULT_SETTINGS, DockerRuntimeSettings
from .errors import WorkspacePolicyError


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_host_workspace(
    raw_path: str | Path,
    settings: DockerRuntimeSettings = DEFAULT_SETTINGS,
) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise WorkspacePolicyError("workspace path must be absolute")
    if not path.exists():
        raise WorkspacePolicyError("workspace path does not exist")
    if not path.is_dir():
        raise WorkspacePolicyError("workspace path must be a directory")

    resolved = path.resolve()
    allowed_roots = tuple(root.expanduser().resolve() for root in settings.allowed_roots)
    deny_roots = tuple(root.expanduser().resolve() for root in settings.deny_roots)

    if allowed_roots and not any(_is_relative_to(resolved, root) for root in allowed_roots):
        raise WorkspacePolicyError("workspace path is outside allowed roots")

    for root in deny_roots:
        if resolved == root:
            raise WorkspacePolicyError(f"workspace path may not be {root}")
        if root != Path("/") and _is_relative_to(resolved, root):
            raise WorkspacePolicyError(f"workspace path may not be under {root}")

    return resolved
