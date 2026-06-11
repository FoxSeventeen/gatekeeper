"""Docker container lifecycle and project binding validation."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CONTAINER_WORKSPACE, DEFAULT_SETTINGS, DockerRuntimeSettings
from .errors import ContainerValidationError
from .project_config import ProjectConfig
from .state_store import ProjectBinding


logger = logging.getLogger(__name__)


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
        cmd = [self.settings.docker_bin, *args]
        logger.info("Gatekeeper Docker 命令开始：cmd=%r timeout=%s input_text_present=%s", cmd, timeout or self.settings.command_timeout_seconds, input_text is not None)
        proc = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout or self.settings.command_timeout_seconds,
            check=False,
        )
        logger.info(
            "Gatekeeper Docker 命令结束：cmd=%r returncode=%s stdout=%r stderr=%r",
            cmd,
            proc.returncode,
            (proc.stdout or "").strip(),
            (proc.stderr or "").strip(),
        )
        return proc

    def inspect_container(self, container_name: str) -> dict[str, Any] | None:
        logger.info("Gatekeeper 容器检查开始：container_name=%s", container_name)
        proc = self._run(["inspect", container_name])
        if proc.returncode != 0:
            logger.info("Gatekeeper 容器检查结果：容器不存在或 inspect 失败 container_name=%s stderr=%r", container_name, (proc.stderr or "").strip())
            return None
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            logger.info("Gatekeeper 容器检查失败：docker inspect 返回非法 JSON container_name=%s error=%s", container_name, exc)
            raise ContainerValidationError(f"docker inspect returned invalid JSON: {exc}") from exc
        logger.info("Gatekeeper 容器检查成功：container_name=%s objects=%s", container_name, len(data) if isinstance(data, list) else "unknown")
        return data[0] if data else None

    def container_exists(self, container_name: str) -> bool:
        return self.inspect_container(container_name) is not None

    def container_running(self, container_name: str) -> bool:
        info = self.inspect_container(container_name)
        return bool(info and info.get("State", {}).get("Running"))

    def start_container(self, container_name: str) -> None:
        logger.info("Gatekeeper 容器启动开始：container_name=%s", container_name)
        proc = self._run(["start", container_name])
        if proc.returncode != 0:
            logger.info("Gatekeeper 容器启动失败：container_name=%s stderr=%r", container_name, (proc.stderr or "").strip())
            raise ContainerValidationError(proc.stderr.strip() or "docker start failed")
        logger.info("Gatekeeper 容器启动成功：container_name=%s", container_name)

    def stop_container(self, container_name: str) -> None:
        proc = self._run(["stop", container_name])
        if proc.returncode != 0:
            raise ContainerValidationError(proc.stderr.strip() or "docker stop failed")

    def remove_container(self, container_name: str, *, force: bool = False) -> None:
        logger.info("Gatekeeper 容器删除开始：container_name=%s force=%s", container_name, force)
        args = ["rm"]
        if force:
            args.append("-f")
        args.append(container_name)
        proc = self._run(args)
        if proc.returncode != 0:
            logger.info("Gatekeeper 容器删除失败：container_name=%s stderr=%r", container_name, (proc.stderr or "").strip())
            raise ContainerValidationError(proc.stderr.strip() or "docker rm failed")
        logger.info("Gatekeeper 容器删除成功：container_name=%s", container_name)

    def create_container(self, config: ProjectConfig, host_workspace: Path) -> None:
        logger.info(
            "Gatekeeper 容器创建开始：container_name=%s project_id=%s image=%s host_workspace=%s container_workspace=%s network=%s",
            config.container_name,
            config.project_id,
            config.image,
            host_workspace,
            CONTAINER_WORKSPACE,
            self.settings.network,
        )
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
                "--mount",
                f"type=bind,source={host_workspace},target={CONTAINER_WORKSPACE}",
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
            logger.info(
                "Gatekeeper 容器创建失败：container_name=%s host_workspace=%s stderr=%r",
                config.container_name,
                host_workspace,
                (proc.stderr or "").strip(),
            )
            raise ContainerValidationError(proc.stderr.strip() or "docker run failed")
        logger.info("Gatekeeper 容器创建成功：container_name=%s docker_stdout=%r", config.container_name, (proc.stdout or "").strip())

    def validate_container_for_project(
        self,
        container_info: dict[str, Any],
        config: ProjectConfig,
        host_workspace: Path,
    ) -> ContainerValidation:
        labels = container_info.get("Config", {}).get("Labels") or {}
        logger.info(
            "Gatekeeper 容器校验开始：container_name=%s expected_project_id=%s expected_host_workspace=%s labels=%s mounts=%s",
            config.container_name,
            config.project_id,
            host_workspace,
            labels,
            container_info.get("Mounts", []),
        )
        if labels.get("hermes.plugin") != "docker-runtime":
            logger.info("Gatekeeper 容器校验失败：hermes.plugin label 不匹配 actual=%s", labels.get("hermes.plugin"))
            return ContainerValidation(False, False, "container label hermes.plugin does not match")
        if labels.get("hermes.project_id") != config.project_id:
            logger.info("Gatekeeper 容器校验失败：project_id label 不匹配 actual=%s expected=%s", labels.get("hermes.project_id"), config.project_id)
            return ContainerValidation(False, False, "container project_id label does not match")
        if labels.get("hermes.binding_mode") != "workspace_config":
            logger.info("Gatekeeper 容器校验失败：binding_mode label 不匹配 actual=%s", labels.get("hermes.binding_mode"))
            return ContainerValidation(False, False, "container binding_mode label does not match")
        if labels.get("hermes.container_workspace") != CONTAINER_WORKSPACE:
            logger.info("Gatekeeper 容器校验失败：container_workspace label 不匹配 actual=%s expected=%s", labels.get("hermes.container_workspace"), CONTAINER_WORKSPACE)
            return ContainerValidation(False, False, "container workspace label does not match")

        expected_source = str(host_workspace)
        for mount in container_info.get("Mounts", []):
            if mount.get("Type") == "bind" and mount.get("Destination") == CONTAINER_WORKSPACE:
                source = str(mount.get("Source", ""))
                if source != expected_source:
                    logger.info(
                        "Gatekeeper 容器校验失败：mount source 不匹配 actual=%s expected=%s destination=%s",
                        source,
                        expected_source,
                        CONTAINER_WORKSPACE,
                    )
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
        logger.info("Gatekeeper 容器校验失败：缺少 /workspace bind mount expected_source=%s", expected_source)
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
