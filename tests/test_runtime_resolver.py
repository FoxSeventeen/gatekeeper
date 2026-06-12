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


class AutoBindContainers:
    def __init__(self):
        self.created = []
        self.ensure_calls = []

    def inspect_container(self, container_name):
        return None

    def create_container(self, config, host_workspace):
        self.created.append((config.container_name, str(host_workspace)))

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


def test_resolve_runtime_uses_default_alias_when_only_tool_call_id_is_present(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    project_id = _insert_binding(store, tmp_path)
    store.upsert_session_alias("default", None, project_id)

    runtime = resolve_runtime(
        store=store,
        containers=HealthyContainers(),
        settings=DockerRuntimeSettings(state_db_path=tmp_path / "state.db"),
        tool_call_id="call-1",
    )

    assert runtime.session_id == "default"
    assert runtime.project_id == project_id


def test_resolve_runtime_prefers_host_path_over_default_alias(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    default_project = _insert_binding(store, tmp_path / "default")
    store.upsert_session_alias("default", None, default_project)
    project = tmp_path / "explicit"
    source = project / "main.cpp"
    source.parent.mkdir(parents=True)
    source.write_text("int main() { return 0; }\n", encoding="utf-8")
    containers = AutoBindContainers()
    settings = DockerRuntimeSettings(
        state_db_path=tmp_path / "state.db",
        deny_roots=(Path("/etc"),),
        docker_probe_enabled=False,
    )

    runtime = resolve_runtime(
        store=store,
        containers=containers,
        settings=settings,
        session_id="real-session",
        candidate_paths=[str(source)],
        allow_auto_bind=True,
    )

    assert runtime.project_id != default_project
    assert runtime.host_workspace == project.resolve()


def test_resolve_runtime_does_not_auto_bind_container_workspace_path(monkeypatch, tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    default_project = _insert_binding(store, tmp_path / "default")
    store.upsert_session_alias("default", None, default_project)
    validated_paths = []

    def fake_existing_anchor(path):
        if str(path).startswith("/workspace"):
            return Path("/workspace")
        return path

    def fake_validate_host_workspace(path, settings):
        validated_paths.append(str(path))
        return Path(path)

    monkeypatch.setattr("gatekeeper.runtime_resolver._existing_anchor", fake_existing_anchor)
    monkeypatch.setattr("gatekeeper.runtime_resolver.validate_host_workspace", fake_validate_host_workspace)

    runtime = resolve_runtime(
        store=store,
        containers=HealthyContainers(),
        settings=DockerRuntimeSettings(state_db_path=tmp_path / "state.db"),
        session_id="tool-call-session",
        candidate_paths=["/workspace/main.cpp"],
        allow_auto_bind=True,
    )

    assert runtime.project_id == default_project
    assert validated_paths == []


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


def test_resolve_runtime_auto_binds_from_host_path_when_session_unset(tmp_path: Path):
    project = tmp_path / "project"
    source = project / "src" / "main.cpp"
    source.parent.mkdir(parents=True)
    source.write_text("int main() { return 0; }\n", encoding="utf-8")
    store = StateStore(tmp_path / "state.db")
    containers = AutoBindContainers()
    settings = DockerRuntimeSettings(
        state_db_path=tmp_path / "state.db",
        deny_roots=(Path("/etc"),),
        docker_probe_enabled=False,
    )

    runtime = resolve_runtime(
        store=store,
        containers=containers,
        settings=settings,
        session_id="s1",
        cwd=str(project),
        candidate_paths=[str(source)],
        allow_auto_bind=True,
    )

    assert runtime.host_workspace == project.resolve()
    assert store.get_project_id_for_session("s1") == runtime.project_id
    assert containers.created == [(runtime.container_name, str(project.resolve()))]
    assert containers.ensure_calls
