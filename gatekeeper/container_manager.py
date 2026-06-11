"""Docker container lifecycle and project binding validation."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CONTAINER_WORKSPACE, DEFAULT_SETTINGS, DockerRuntimeSettings
from .errors import ContainerValidationError
from .project_config import ProjectConfig
from .state_store import ProjectBinding


@dataclass
class ContainerValidation:
    ok: bool
    running: bool
    message: str
    mount_source: str | None = None
    mount_destination: str | None = None


class ContainerManager:
    def __init__(self, settings: DockerRuntimeSettings = DEFAULT_SETTINGS):
        self.settings = settings

    def _run(self, args: list[str], *, input_text: str | None = None, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.settings.docker_bin, *args],
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout or self.settings.command_timeout_seconds,
            check=False,
        )

    def inspect_container(self, container_name: str) -> dict[str, Any] | None:
        proc = self._run(["inspect", container_name])
        if proc.returncode != 0:
            return None
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise ContainerValidationError(f"docker inspect returned invalid JSON: {exc}") from exc
        return data[0] if data else None

    def container_exists(self, container_name: str) -> bool:
        return self.inspect_container(container_name) is not None

    def container_running(self, container_name: str) -> bool:
        info = self.inspect_container(container_name)
        return bool(info and info.get("State", {}).get("Running"))

    def start_container(self, container_name: str) -> None:
        proc = self._run(["start", container_name])
        if proc.returncode != 0:
            raise ContainerValidationError(proc.stderr.strip() or "docker start failed")

    def stop_container(self, container_name: str) -> None:
        proc = self._run(["stop", container_name])
        if proc.returncode != 0:
            raise ContainerValidationError(proc.stderr.strip() or "docker stop failed")

    def remove_container(self, container_name: str, *, force: bool = False) -> None:
        args = ["rm"]
        if force:
            args.append("-f")
        args.append(container_name)
        proc = self._run(args)
        if proc.returncode != 0:
            raise ContainerValidationError(proc.stderr.strip() or "docker rm failed")

    def create_container(self, config: ProjectConfig, host_workspace: Path) -> None:
        proc = self._run(
            [
                "run",
                "-d",
                "--name",
                config.container_name,
                "--label",
                "hermes.plugin=docker-runtime",
                "--label",
                f"hermes.project_id={config.project_id}",
                "--label",
                "hermes.binding_mode=workspace_config",
                "--label",
                f"hermes.container_workspace={CONTAINER_WORKSPACE}",
                "--label",
                f"hermes.image={config.image}",
                "-v",
                f"{host_workspace}:{CONTAINER_WORKSPACE}",
                "-w",
                CONTAINER_WORKSPACE,
                "--network",
                self.settings.network,
                config.image,
                "sleep",
                "infinity",
            ]
        )
        if proc.returncode != 0:
            raise ContainerValidationError(proc.stderr.strip() or "docker run failed")

    def validate_container_for_project(
        self,
        container_info: dict[str, Any],
        config: ProjectConfig,
        host_workspace: Path,
    ) -> ContainerValidation:
        labels = container_info.get("Config", {}).get("Labels") or {}
        if labels.get("hermes.plugin") != "docker-runtime":
            return ContainerValidation(False, False, "container label hermes.plugin does not match")
        if labels.get("hermes.project_id") != config.project_id:
            return ContainerValidation(False, False, "container project_id label does not match")
        if labels.get("hermes.binding_mode") != "workspace_config":
            return ContainerValidation(False, False, "container binding_mode label does not match")
        if labels.get("hermes.container_workspace") != CONTAINER_WORKSPACE:
            return ContainerValidation(False, False, "container workspace label does not match")

        expected_source = str(host_workspace.resolve())
        for mount in container_info.get("Mounts", []):
            if mount.get("Destination") == CONTAINER_WORKSPACE:
                source = str(Path(mount.get("Source", "")).resolve())
                if source != expected_source:
                    return ContainerValidation(
                        False,
                        bool(container_info.get("State", {}).get("Running")),
                        "container mount source does not match current workspace",
                        mount_source=source,
                        mount_destination=CONTAINER_WORKSPACE,
                    )
                return ContainerValidation(
                    True,
                    bool(container_info.get("State", {}).get("Running")),
                    "container labels and mounts match",
                    mount_source=source,
                    mount_destination=CONTAINER_WORKSPACE,
                )
        return ContainerValidation(False, False, "container is missing /workspace mount")

    def ensure_container_for_binding(self, binding: ProjectBinding, config: ProjectConfig) -> ContainerValidation:
        info = self.inspect_container(binding.container_name)
        if info is None:
            raise ContainerValidationError("container does not exist")
        validation = self.validate_container_for_project(info, config, Path(binding.host_workspace))
        if not validation.ok:
            raise ContainerValidationError(validation.message)
        if not validation.running:
            self.start_container(binding.container_name)
            validation.running = True
        return validation
