"""Resolve the current session to a validated Docker runtime."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .config import CONTAINER_WORKSPACE, DEFAULT_SETTINGS, DockerRuntimeSettings
from .container_manager import ContainerManager
from .errors import WorkspaceNotSet
from .project_config import config_path_for_workspace, create_project_config, read_project_config, write_project_config
from .session_resolver import root_session_id_from_context, session_id_from_context
from .state_store import ProjectBinding, StateStore
from .workspace_policy import validate_host_workspace


logger = logging.getLogger(__name__)


@dataclass
class DockerRuntime:
    session_id: str
    project_id: str
    container_name: str
    host_workspace: Path
    container_workspace: str = CONTAINER_WORKSPACE


def resolve_runtime(
    *,
    store: StateStore | None = None,
    containers: ContainerManager | None = None,
    settings: DockerRuntimeSettings = DEFAULT_SETTINGS,
    candidate_paths: Sequence[str] | None = None,
    allow_auto_bind: bool = False,
    **context,
) -> DockerRuntime:
    session_id = session_id_from_context(context)
    logger.info("Gatekeeper runtime 解析开始：session_id=%s context_keys=%s", session_id, sorted(context.keys()))
    store = store or StateStore(settings.state_db_path)
    containers = containers or ContainerManager(settings)
    project_id = store.get_project_id_for_session(session_id)
    logger.info("Gatekeeper runtime 查询 session alias：session_id=%s project_id=%s", session_id, project_id)
    host_candidate_paths = _host_candidate_paths(candidate_paths or [])
    if candidate_paths and len(host_candidate_paths) != len(candidate_paths):
        logger.info(
            "Gatekeeper runtime 已过滤非宿主路径候选：original=%s filtered=%s",
            list(candidate_paths),
            host_candidate_paths,
        )
    if not project_id and allow_auto_bind and host_candidate_paths:
        logger.info(
            "Gatekeeper runtime 当前 session 未绑定，优先尝试根据工具参数中的宿主路径自动绑定：session_id=%s candidate_paths=%s",
            session_id,
            host_candidate_paths,
        )
        runtime = resolve_runtime_from_candidate_paths(
            host_candidate_paths,
            store=store,
            containers=containers,
            settings=settings,
            session_id=session_id,
            root_session_id=root_session_id_from_context(context),
            context=context,
        )
        if runtime:
            return runtime
    if not project_id and session_id != "default":
        project_id = store.get_project_id_for_session("default")
        logger.info("Gatekeeper runtime 回退查询 default alias：original_session_id=%s default_project_id=%s", session_id, project_id)
    if not project_id:
        logger.info("Gatekeeper runtime 解析失败：没有找到 session alias session_id=%s", session_id)
        raise WorkspaceNotSet("Workspace is not set. Ask the user to run /workspace set <absolute_host_path> before using docker tools.")
    binding = store.get_project_binding(project_id)
    if not binding:
        logger.info("Gatekeeper runtime 解析失败：state.db 缺少 project binding project_id=%s", project_id)
        raise WorkspaceNotSet("Workspace binding is missing from state.db. Ask the user to run /workspace repair.")
    return runtime_from_binding(binding, containers, session_id=session_id)


def _host_candidate_paths(candidate_paths: Sequence[str]) -> list[str]:
    paths: list[str] = []
    for raw_path in candidate_paths:
        path = str(raw_path)
        if path == CONTAINER_WORKSPACE or path.startswith(CONTAINER_WORKSPACE + "/"):
            continue
        paths.append(path)
    return paths


def resolve_runtime_from_candidate_paths(
    candidate_paths: Sequence[str],
    *,
    store: StateStore,
    containers: ContainerManager,
    settings: DockerRuntimeSettings,
    session_id: str,
    root_session_id: str | None,
    context: dict,
) -> DockerRuntime | None:
    host_workspace = infer_host_workspace(candidate_paths, context)
    logger.info(
        "Gatekeeper runtime 自动绑定推断结果：session_id=%s host_workspace=%s candidate_paths=%s",
        session_id,
        host_workspace,
        list(candidate_paths),
    )
    if not host_workspace:
        return None

    host_workspace = validate_host_workspace(host_workspace, settings)
    config = read_project_config(host_workspace)
    created_config = False
    if config is None:
        logger.info("Gatekeeper runtime 自动绑定：未找到项目配置，将创建 host_workspace=%s image=%s", host_workspace, settings.image)
        config = create_project_config(host_workspace, settings.image)
        write_project_config(host_workspace, config)
        created_config = True

    binding = store.get_project_binding(config.project_id)
    if binding and binding.host_workspace != str(host_workspace):
        logger.info(
            "Gatekeeper runtime 自动绑定拒绝：state.db host_workspace 与推断路径不一致 project_id=%s binding_host=%s inferred_host=%s",
            config.project_id,
            binding.host_workspace,
            host_workspace,
        )
        raise WorkspaceNotSet("Workspace binding host path differs from the inferred path. Ask the user to run /workspace set.")

    info = containers.inspect_container(config.container_name)
    if info is None:
        logger.info(
            "Gatekeeper runtime 自动绑定：容器不存在，准备创建 container_name=%s host_workspace=%s",
            config.container_name,
            host_workspace,
        )
        containers.create_container(config, host_workspace)
    else:
        validation = containers.validate_container_for_project(info, config, host_workspace)
        logger.info(
            "Gatekeeper runtime 自动绑定：已有容器校验结果 ok=%s running=%s message=%s",
            validation.ok,
            validation.running,
            validation.message,
        )
        if not validation.ok:
            raise WorkspaceNotSet(f"Workspace container does not match inferred path: {validation.message}.")
        if not validation.running:
            containers.start_container(config.container_name)

    now = time.time()
    store.upsert_project_binding(
        ProjectBinding(
            project_id=config.project_id,
            container_name=config.container_name,
            image=config.image,
            host_workspace=str(host_workspace),
            config_path=str(config_path_for_workspace(host_workspace)),
            container_workspace=config.container_workspace,
            logical_workspace=config.logical_workspace,
            state="active",
            created_at=now,
            updated_at=now,
            last_used_at=now,
        )
    )
    store.upsert_session_alias(session_id, root_session_id, config.project_id)
    store.update_last_used_at(config.project_id)
    logger.info(
        "Gatekeeper runtime 自动绑定完成：session_id=%s project_id=%s container_name=%s host_workspace=%s created_config=%s",
        session_id,
        config.project_id,
        config.container_name,
        host_workspace,
        created_config,
    )
    binding = store.get_project_binding(config.project_id)
    if binding is None:
        raise WorkspaceNotSet("Workspace auto-bind failed to persist project binding.")
    return runtime_from_binding(binding, containers, session_id=session_id)


def infer_host_workspace(candidate_paths: Sequence[str], context: dict | None = None) -> Path | None:
    context_roots = _context_workspace_roots(context or {})
    for raw_path in candidate_paths:
        candidate = Path(str(raw_path)).expanduser()
        if not candidate.is_absolute():
            continue
        if not candidate.exists():
            resolved_candidate = candidate.resolve(strict=False)
            for root in context_roots:
                try:
                    resolved_candidate.relative_to(root.resolve())
                except ValueError:
                    continue
                return root
            logger.info("Gatekeeper runtime 自动绑定跳过不存在路径：candidate=%s", candidate)
            continue
        anchor = _existing_anchor(candidate)
        config_root = _nearest_config_root(anchor)
        if config_root:
            return config_root
        for root in context_roots:
            try:
                anchor.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            return root
        if anchor.is_file():
            return anchor.parent
        return anchor
    return None


def _existing_anchor(path: Path) -> Path:
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def _nearest_config_root(anchor: Path) -> Path | None:
    current = anchor.parent if anchor.is_file() else anchor
    for candidate in (current, *current.parents):
        if config_path_for_workspace(candidate).exists():
            return candidate
    return None


def _context_workspace_roots(context: dict) -> list[Path]:
    roots: list[Path] = []
    for key in ("cwd", "current_dir", "current_directory", "workspace", "workspace_path", "project_path"):
        value = context.get(key)
        if not value:
            continue
        root = Path(str(value)).expanduser()
        if root.is_absolute() and root.exists() and root.is_dir():
            roots.append(root)
    return roots


def runtime_from_binding(
    binding: ProjectBinding,
    containers: ContainerManager,
    *,
    session_id: str = "",
) -> DockerRuntime:
    host_workspace = Path(binding.host_workspace)
    logger.info(
        "Gatekeeper runtime binding 校验开始：session_id=%s project_id=%s container_name=%s host_workspace=%s config_path=%s",
        session_id,
        binding.project_id,
        binding.container_name,
        binding.host_workspace,
        binding.config_path,
    )
    config = read_project_config(host_workspace)
    if config is None:
        logger.info("Gatekeeper runtime binding 校验失败：项目配置缺失 host_workspace=%s", host_workspace)
        raise WorkspaceNotSet("Project config is missing. Ask the user to run /workspace set <absolute_host_path>.")
    containers.ensure_container_for_binding(binding, config)
    logger.info(
        "Gatekeeper runtime binding 校验完成：session_id=%s project_id=%s container_name=%s container_workspace=%s",
        session_id,
        binding.project_id,
        binding.container_name,
        binding.container_workspace,
    )
    return DockerRuntime(
        session_id=session_id,
        project_id=binding.project_id,
        container_name=binding.container_name,
        host_workspace=host_workspace,
        container_workspace=binding.container_workspace,
    )
