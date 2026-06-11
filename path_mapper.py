"""Map structured tool path arguments into `/workspace` container paths."""

from __future__ import annotations

from pathlib import PurePosixPath, Path

from .config import CONTAINER_WORKSPACE
from .errors import ProtectedPathError, WorkspacePolicyError


class PathMapper:
    def __init__(self, host_workspace: Path, container_workspace: str = CONTAINER_WORKSPACE):
        self.host_workspace = host_workspace.resolve()
        self.container_workspace = PurePosixPath(container_workspace)

    def to_container(self, raw_path: str | Path) -> str:
        raw = str(raw_path)
        if not raw:
            raise WorkspacePolicyError("path may not be empty")
        if raw.startswith(str(self.container_workspace)):
            rel = PurePosixPath(raw).relative_to(self.container_workspace)
        else:
            candidate = Path(raw).expanduser()
            if candidate.is_absolute():
                resolved = candidate.resolve()
                try:
                    rel_host = resolved.relative_to(self.host_workspace)
                except ValueError as exc:
                    raise WorkspacePolicyError("absolute path is outside workspace") from exc
                rel = PurePosixPath(rel_host.as_posix())
            else:
                rel = PurePosixPath(raw)
        normalized = PurePosixPath("/")
        for part in rel.parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise WorkspacePolicyError("path traversal outside workspace is not allowed")
            normalized /= part
        return str(self.container_workspace / normalized.relative_to("/"))

    def assert_writable(self, raw_path: str | Path) -> None:
        container_path = PurePosixPath(self.to_container(raw_path))
        protected_dir = self.container_workspace / ".hermes"
        if container_path == protected_dir or protected_dir in container_path.parents:
            raise ProtectedPathError("file tools may not modify /workspace/.hermes metadata")

    def to_logical(self, raw_path: str | Path) -> str:
        return self.to_container(raw_path)
