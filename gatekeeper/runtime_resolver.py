"""Resolve the current session to a validated Docker runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import CONTAINER_WORKSPACE, DEFAULT_SETTINGS, DockerRuntimeSettings
from .container_manager import ContainerManager
from .errors import WorkspaceNotSet
from .project_config import read_project_config
from .session_resolver import session_id_from_context
from .state_store import ProjectBinding, StateStore


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
    **context,
) -> DockerRuntime:
    session_id = session_id_from_context(context)
    store = store or StateStore(settings.state_db_path)
    containers = containers or ContainerManager(settings)
    project_id = store.get_project_id_for_session(session_id)
    if not project_id:
        raise WorkspaceNotSet("Workspace is not set. Ask the user to run /workspace set <absolute_host_path>.")
    binding = store.get_project_binding(project_id)
    if not binding:
        raise WorkspaceNotSet("Workspace binding is missing from state.db. Ask the user to run /workspace repair.")
    return runtime_from_binding(binding, containers)


def runtime_from_binding(binding: ProjectBinding, containers: ContainerManager) -> DockerRuntime:
    host_workspace = Path(binding.host_workspace)
    config = read_project_config(host_workspace)
    if config is None:
        raise WorkspaceNotSet("Project config is missing. Ask the user to run /workspace set <absolute_host_path>.")
    containers.ensure_container_for_binding(binding, config)
    return DockerRuntime(
        session_id="",
        project_id=binding.project_id,
        container_name=binding.container_name,
        host_workspace=host_workspace,
        container_workspace=binding.container_workspace,
    )
