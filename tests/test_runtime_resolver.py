import time
from pathlib import Path

import pytest

from gatekeeper.config import DockerRuntimeSettings
from gatekeeper.errors import WorkspaceNotSet
from gatekeeper.project_config import create_project_config, write_project_config
from gatekeeper.runtime_resolver import resolve_runtime
from gatekeeper.state_store import ProjectBinding, StateStore


class HealthyContainers:
    def __init__(self):
        self.ensure_calls = []

    def ensure_container_for_binding(self, binding, config):
        self.ensure_calls.append((binding, config))


def _insert_binding(store: StateStore, workspace: Path) -> str:
    config = create_project_config(workspace)
    write_project_config(workspace, config)
    now = time.time()
    store.upsert_project_binding(
        ProjectBinding(
            project_id=config.project_id,
            container_name=config.container_name,
            image=config.image,
            host_workspace=str(workspace),
            config_path=str(workspace / ".hermes" / "docker-runtime.json"),
            container_workspace=config.container_workspace,
            logical_workspace=config.logical_workspace,
            state="active",
            created_at=now,
            updated_at=now,
            last_used_at=now,
        )
    )
    return config.project_id


def test_resolve_runtime_preserves_session_id(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    project_id = _insert_binding(store, tmp_path)
    store.upsert_session_alias("s1", None, project_id)
    containers = HealthyContainers()

    runtime = resolve_runtime(
        store=store,
        containers=containers,
        settings=DockerRuntimeSettings(state_db_path=tmp_path / "state.db"),
        session_id="s1",
    )

    assert runtime.session_id == "s1"
    assert runtime.project_id == project_id
    assert containers.ensure_calls


def test_resolve_runtime_falls_back_to_default_alias(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    project_id = _insert_binding(store, tmp_path)
    store.upsert_session_alias("default", None, project_id)

    runtime = resolve_runtime(
        store=store,
        containers=HealthyContainers(),
        settings=DockerRuntimeSettings(state_db_path=tmp_path / "state.db"),
        session_id="real-session",
    )

    assert runtime.session_id == "real-session"
    assert runtime.project_id == project_id


def test_resolve_runtime_does_not_fallback_when_session_has_binding(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    default_project = _insert_binding(store, tmp_path / "default")
    specific_project = _insert_binding(store, tmp_path / "specific")
    store.upsert_session_alias("default", None, default_project)
    store.upsert_session_alias("real-session", None, specific_project)

    runtime = resolve_runtime(
        store=store,
        containers=HealthyContainers(),
        settings=DockerRuntimeSettings(state_db_path=tmp_path / "state.db"),
        session_id="real-session",
    )

    assert runtime.project_id == specific_project


def test_resolve_runtime_still_fails_without_any_alias(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")

    with pytest.raises(WorkspaceNotSet):
        resolve_runtime(
            store=store,
            containers=HealthyContainers(),
            settings=DockerRuntimeSettings(state_db_path=tmp_path / "state.db"),
            session_id="missing",
        )
