from pathlib import Path

from gatekeeper.config import DockerRuntimeSettings
from gatekeeper.container_manager import ContainerValidation
from gatekeeper.project_config import create_project_config, write_project_config
from gatekeeper.state_store import StateStore
from gatekeeper.workspace_commands import WorkspaceCommandHandler


class FakeContainers:
    def __init__(self, inspected=None, validation=None):
        self.created = []
        self.started = []
        self.inspected = inspected
        self.validation = validation

    def inspect_container(self, container_name):
        return self.inspected

    def create_container(self, config, host_workspace):
        self.created.append((config.container_name, str(host_workspace)))

    def validate_container_for_project(self, info, config, host_workspace):
        if self.validation is None:
            raise AssertionError("not called for missing container")
        return self.validation

    def start_container(self, container_name):
        self.started.append(container_name)


def test_workspace_set_initializes_project(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    containers = FakeContainers()
    settings = DockerRuntimeSettings(
        state_db_path=tmp_path / "state.db",
        deny_roots=(Path("/etc"),),
    )
    handler = WorkspaceCommandHandler(store, containers, settings)

    result = handler.handle(f"set {tmp_path}", session_id="s1")

    assert "LOCKED" in result
    assert (tmp_path / ".hermes" / "docker-runtime.json").exists()
    assert containers.created
    project_id = store.get_project_id_for_session("s1")
    assert project_id
    assert store.get_project_binding(project_id)


def test_workspace_set_without_session_context_creates_default_alias(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    containers = FakeContainers()
    settings = DockerRuntimeSettings(
        state_db_path=tmp_path / "state.db",
        deny_roots=(Path("/etc"),),
    )
    handler = WorkspaceCommandHandler(store, containers, settings)

    result = handler.handle(f"set {tmp_path}")

    assert "LOCKED" in result
    assert store.get_project_id_for_session("default")


def test_workspace_set_imports_config_and_recreates_missing_container(tmp_path: Path):
    config = create_project_config(tmp_path)
    write_project_config(tmp_path, config)
    store = StateStore(tmp_path / "state.db")
    containers = FakeContainers()
    settings = DockerRuntimeSettings(state_db_path=tmp_path / "state.db", deny_roots=(Path("/etc"),))
    handler = WorkspaceCommandHandler(store, containers, settings)

    result = handler.handle(f"set {tmp_path}", session_id="s1")

    assert "imported project config" in result
    assert "recreated missing Docker container" in result
    assert containers.created == [(config.container_name, str(tmp_path.resolve()))]
    assert store.get_project_binding(config.project_id)


def test_workspace_set_adopts_existing_matching_container(tmp_path: Path):
    config = create_project_config(tmp_path)
    write_project_config(tmp_path, config)
    validation = ContainerValidation(True, False, "container labels and mounts match")
    store = StateStore(tmp_path / "state.db")
    containers = FakeContainers(inspected={"State": {"Running": False}}, validation=validation)
    settings = DockerRuntimeSettings(state_db_path=tmp_path / "state.db", deny_roots=(Path("/etc"),))
    handler = WorkspaceCommandHandler(store, containers, settings)

    result = handler.handle(f"set {tmp_path}", session_id="s1")

    assert "imported project config" in result
    assert "adopted existing Docker container" in result
    assert containers.started == [config.container_name]
    assert not containers.created


def test_workspace_set_rejects_label_mismatch_for_foreign_config(tmp_path: Path):
    config = create_project_config(tmp_path)
    write_project_config(tmp_path, config)
    validation = ContainerValidation(False, False, "container project_id label does not match")
    store = StateStore(tmp_path / "state.db")
    containers = FakeContainers(inspected={"State": {"Running": False}}, validation=validation)
    settings = DockerRuntimeSettings(state_db_path=tmp_path / "state.db", deny_roots=(Path("/etc"),))
    handler = WorkspaceCommandHandler(store, containers, settings)

    result = handler.handle(f"set {tmp_path}", session_id="s1")

    assert result.startswith("REJECTED")
    assert "label" in result
    assert not store.get_project_binding(config.project_id)


def test_workspace_set_rejects_mount_mismatch_for_foreign_config(tmp_path: Path):
    config = create_project_config(tmp_path)
    write_project_config(tmp_path, config)
    validation = ContainerValidation(False, True, "container mount source does not match current workspace")
    store = StateStore(tmp_path / "state.db")
    containers = FakeContainers(inspected={"State": {"Running": True}}, validation=validation)
    settings = DockerRuntimeSettings(state_db_path=tmp_path / "state.db", deny_roots=(Path("/etc"),))
    handler = WorkspaceCommandHandler(store, containers, settings)

    result = handler.handle(f"set {tmp_path}", session_id="s1")

    assert result.startswith("REJECTED")
    assert "mount" in result
    assert "recreate" in result
    assert not store.get_project_binding(config.project_id)
