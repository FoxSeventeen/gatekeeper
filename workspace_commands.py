"""Implementation of `/workspace ...` slash commands."""

from __future__ import annotations

import logging
import shlex
import time
from pathlib import Path

from .config import DEFAULT_SETTINGS, DockerRuntimeSettings
from .container_manager import ContainerManager
from .errors import DockerRuntimeError
from .project_config import (
    ProjectConfig,
    config_path_for_workspace,
    container_name_for_project,
    create_project_config,
    read_project_config,
    utc_now_iso,
    write_project_config,
)
from .session_resolver import root_session_id_from_context, session_id_from_context
from .state_store import ProjectBinding, StateStore
from .workspace_policy import validate_host_workspace


logger = logging.getLogger(__name__)


def _binding_from_config(config: ProjectConfig, host_workspace: Path, state: str = "active") -> ProjectBinding:
    now = time.time()
    return ProjectBinding(
        project_id=config.project_id,
        container_name=config.container_name,
        image=config.image,
        host_workspace=str(host_workspace),
        config_path=str(config_path_for_workspace(host_workspace)),
        container_workspace=config.container_workspace,
        logical_workspace=config.logical_workspace,
        state=state,
        created_at=now,
        updated_at=now,
        last_used_at=now,
    )


class WorkspaceCommandHandler:
    def __init__(
        self,
        store: StateStore | None = None,
        containers: ContainerManager | None = None,
        settings: DockerRuntimeSettings = DEFAULT_SETTINGS,
    ):
        self.settings = settings
        self.store = store or StateStore(settings.state_db_path)
        self.containers = containers or ContainerManager(settings)
        self._last_workspace_by_session: dict[str, Path] = {}

    def handle(self, raw_args: str, **context) -> str:
        logger.info("Gatekeeper /workspace 命令入口：raw_args=%r context_keys=%s", raw_args, sorted(context.keys()))
        try:
            parts = shlex.split(raw_args or "")
        except ValueError as exc:
            logger.info("Gatekeeper /workspace 参数解析失败：raw_args=%r error=%s", raw_args, exc)
            return f"Invalid /workspace arguments: {exc}"
        if not parts or parts[0] == "help":
            logger.info("Gatekeeper /workspace 返回帮助：parts=%s", parts)
            return workspace_help()
        cmd, rest = parts[0], parts[1:]
        logger.info("Gatekeeper /workspace 命令解析完成：cmd=%s rest=%s", cmd, rest)
        try:
            if cmd == "set":
                if len(rest) != 1:
                    return "Usage: /workspace set <absolute_host_path>"
                return self.workspace_set(rest[0], **context)
            if cmd == "status":
                return self.workspace_status(**context)
            if cmd == "reset":
                return self.workspace_reset(**context)
            if cmd == "recreate":
                return self.workspace_recreate(**context)
            if cmd == "repair":
                return self.workspace_repair(**context)
            if cmd == "fork":
                return "Workspace fork is reserved for a later phase. Use /workspace recreate for local container rebuilds."
            return f"Unknown /workspace command: {cmd}\n\n{workspace_help()}"
        except DockerRuntimeError as exc:
            logger.info("Gatekeeper /workspace 命令失败：cmd=%s rest=%s error=%s", cmd, rest, exc)
            return f"Workspace error: {exc}"

    def workspace_set(self, raw_path: str, **context) -> str:
        session_id = session_id_from_context(context)
        root_session_id = root_session_id_from_context(context)
        logger.info(
            "Gatekeeper /workspace set 开始：raw_path=%r session_id=%s root_session_id=%s",
            raw_path,
            session_id,
            root_session_id,
        )
        host_workspace = validate_host_workspace(raw_path, self.settings)
        logger.info("Gatekeeper /workspace set：工作区路径校验通过 host_workspace=%s", host_workspace)
        self._last_workspace_by_session[session_id] = host_workspace

        config_path = config_path_for_workspace(host_workspace)
        logger.info("Gatekeeper /workspace set：准备读取项目配置 config_path=%s", config_path)
        config = read_project_config(host_workspace)
        created_config = False
        if config is None:
            logger.info("Gatekeeper /workspace set：未找到项目配置，将创建新配置 host_workspace=%s image=%s", host_workspace, self.settings.image)
            config = create_project_config(host_workspace, self.settings.image)
            write_project_config(host_workspace, config)
            created_config = True
            logger.info(
                "Gatekeeper /workspace set：新项目配置已写入 project_id=%s container_name=%s config_path=%s",
                config.project_id,
                config.container_name,
                config_path,
            )
        else:
            logger.info(
                "Gatekeeper /workspace set：读取到已有项目配置 project_id=%s container_name=%s config_path=%s",
                config.project_id,
                config.container_name,
                config_path,
            )

        binding = self.store.get_project_binding(config.project_id)
        imported_config = config is not None and not created_config and binding is None
        logger.info(
            "Gatekeeper /workspace set：查询 state.db 绑定 project_id=%s binding_exists=%s imported_config=%s",
            config.project_id,
            binding is not None,
            imported_config,
        )
        if binding:
            logger.info(
                "Gatekeeper /workspace set：已有绑定详情 project_id=%s binding_container=%s binding_host_workspace=%s current_host_workspace=%s",
                binding.project_id,
                binding.container_name,
                binding.host_workspace,
                host_workspace,
            )
            if binding.container_name != config.container_name:
                logger.info("Gatekeeper /workspace set 拒绝：项目配置与 state.db 的 container_name 不一致")
                return "BROKEN: project config and state.db container_name differ. Run /workspace recreate."
            if binding.host_workspace != str(host_workspace):
                logger.info("Gatekeeper /workspace set 拒绝：项目配置与 state.db 的 host_workspace 不一致")
                return "BROKEN: state.db host workspace differs from current path. Run /workspace recreate."

        logger.info("Gatekeeper /workspace set：准备 inspect 容器 container_name=%s", config.container_name)
        info = self.containers.inspect_container(config.container_name)
        if info is None:
            logger.info("Gatekeeper /workspace set：容器不存在，准备创建 container_name=%s host_workspace=%s", config.container_name, host_workspace)
            self.containers.create_container(config, host_workspace)
            action = "created Docker container"
            if imported_config:
                action = "recreated missing Docker container from imported project config"
            logger.info("Gatekeeper /workspace set：容器创建完成 container_name=%s action=%s", config.container_name, action)
        else:
            logger.info("Gatekeeper /workspace set：容器已存在，准备校验 labels/mounts container_name=%s", config.container_name)
            validation = self.containers.validate_container_for_project(info, config, host_workspace)
            logger.info(
                "Gatekeeper /workspace set：容器校验结果 ok=%s running=%s message=%s mount_source=%s mount_destination=%s",
                validation.ok,
                validation.running,
                validation.message,
                validation.mount_source,
                validation.mount_destination,
            )
            if not validation.ok:
                logger.info("Gatekeeper /workspace set 拒绝：已有容器不匹配 message=%s", validation.message)
                return f"REJECTED: {validation.message}. Run /workspace recreate."
            if not validation.running:
                logger.info("Gatekeeper /workspace set：容器未运行，准备启动 container_name=%s", config.container_name)
                self.containers.start_container(config.container_name)
                logger.info("Gatekeeper /workspace set：容器启动完成 container_name=%s", config.container_name)
            action = "reused existing Docker container"
            if imported_config:
                action = "adopted existing Docker container from imported project config"

        logger.info("Gatekeeper /workspace set：准备写入 state.db 项目绑定和 session alias project_id=%s session_id=%s", config.project_id, session_id)
        self.store.upsert_project_binding(_binding_from_config(config, host_workspace))
        self.store.upsert_session_alias(session_id, root_session_id, config.project_id)
        self.store.update_last_used_at(config.project_id)
        logger.info("Gatekeeper /workspace set 完成：project_id=%s container_name=%s action=%s", config.project_id, config.container_name, action)

        if created_config:
            origin = "initialized new project config"
        elif imported_config:
            origin = "imported project config"
        else:
            origin = "loaded known project config"
        return (
            f"LOCKED: workspace bound to Docker runtime\n"
            f"- {origin}\n"
            f"- project_id: {config.project_id}\n"
            f"- container_name: {config.container_name}\n"
            f"- action: {action}\n"
            f"- container_workspace: /workspace"
        )

    def workspace_status(self, **context) -> str:
        session_id = session_id_from_context(context)
        project_id = self.store.get_project_id_for_session(session_id)
        if not project_id:
            return "UNBOUND: current session has no workspace. Run /workspace set <absolute_host_path>."
        binding = self.store.get_project_binding(project_id)
        if not binding:
            return f"BROKEN: session points to {project_id}, but state.db has no project binding."
        host_workspace = Path(binding.host_workspace)
        config = read_project_config(host_workspace)
        if not config:
            return f"BROKEN: missing project config at {binding.config_path}."
        info = self.containers.inspect_container(binding.container_name)
        docker_status = "missing"
        if info:
            validation = self.containers.validate_container_for_project(info, config, host_workspace)
            docker_status = "running" if validation.ok and validation.running else validation.message
        return (
            "Session status: LOCKED\n"
            f"- session_id: {session_id}\n"
            f"- project_id: {project_id}\n"
            f"- config_path: {binding.config_path}\n"
            f"- host_workspace: {binding.host_workspace}\n"
            f"- container_name: {binding.container_name}\n"
            f"- state: {binding.state}\n"
            f"- docker: {docker_status}"
        )

    def workspace_reset(self, **context) -> str:
        session_id = session_id_from_context(context)
        self.store.delete_session_alias(session_id)
        self._last_workspace_by_session.pop(session_id, None)
        return "UNBOUND: current session workspace alias was reset. Project config, state.db binding, and container were not deleted."

    def workspace_recreate(self, **context) -> str:
        session_id = session_id_from_context(context)
        project_id = self.store.get_project_id_for_session(session_id)
        if not project_id:
            return "UNBOUND: run /workspace set <absolute_host_path> before /workspace recreate."
        binding = self.store.get_project_binding(project_id)
        if not binding:
            return "BROKEN: no state.db project binding to recreate."
        host_workspace = validate_host_workspace(binding.host_workspace, self.settings)
        config = read_project_config(host_workspace)
        if not config:
            return "BROKEN: missing project config; run /workspace set again."

        info = self.containers.inspect_container(config.container_name)
        if info is not None:
            validation = self.containers.validate_container_for_project(info, config, host_workspace)
            if validation.ok:
                self.containers.remove_container(config.container_name, force=True)
            else:
                config.container_name = container_name_for_project(config.project_id) + f"-{int(time.time())}"
        config.updated_at = utc_now_iso()
        config.host_workspace_hint = str(host_workspace)
        write_project_config(host_workspace, config)
        self.containers.create_container(config, host_workspace)
        self.store.upsert_project_binding(_binding_from_config(config, host_workspace))
        self.store.upsert_session_alias(session_id, root_session_id_from_context(context), config.project_id)
        return f"LOCKED: recreated Docker container {config.container_name} for project {config.project_id}."

    def workspace_repair(self, **context) -> str:
        session_id = session_id_from_context(context)
        project_id = self.store.get_project_id_for_session(session_id)
        if not project_id:
            return "UNBOUND: run /workspace set <absolute_host_path> before /workspace repair."
        binding = self.store.get_project_binding(project_id)
        if not binding:
            return "BROKEN: missing state.db binding; run /workspace set <absolute_host_path>."
        config = read_project_config(Path(binding.host_workspace))
        if not config:
            return "BROKEN: missing project config; cannot repair automatically."
        info = self.containers.inspect_container(binding.container_name)
        if info is None:
            self.containers.create_container(config, Path(binding.host_workspace))
            return f"LOCKED: missing container recreated as {binding.container_name}."
        validation = self.containers.validate_container_for_project(info, config, Path(binding.host_workspace))
        if not validation.ok:
            return f"REJECTED: {validation.message}. Run /workspace recreate."
        if not validation.running:
            self.containers.start_container(binding.container_name)
            return f"LOCKED: container {binding.container_name} was started."
        return "LOCKED: workspace binding is healthy."


def workspace_help() -> str:
    return (
        "Usage:\n"
        "  /workspace set <absolute_host_path>\n"
        "  /workspace status\n"
        "  /workspace reset\n"
        "  /workspace recreate\n"
        "  /workspace repair\n"
        "  /workspace fork\n\n"
        "workspace must be set directly by the user through this slash command. "
        "After binding, the host project is mounted in Docker at /workspace."
    )


_DEFAULT_HANDLER: WorkspaceCommandHandler | None = None


def handle_workspace_command(raw_args: str, **context) -> str:
    global _DEFAULT_HANDLER
    if _DEFAULT_HANDLER is None:
        _DEFAULT_HANDLER = WorkspaceCommandHandler()
    return _DEFAULT_HANDLER.handle(raw_args, **context)
