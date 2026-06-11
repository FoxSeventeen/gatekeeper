from pathlib import Path

from gatekeeper.config import DockerRuntimeSettings
from gatekeeper.state_store import StateStore
from gatekeeper.workspace_commands import WorkspaceCommandHandler


class FakeContainers:
    def __init__(self):
        self.created = []

    def inspect_container(self, container_name):
        return None

    def create_container(self, config, host_workspace):
        self.created.append((config.container_name, str(host_workspace)))

    def validate_container_for_project(self, info, config, host_workspace):
        raise AssertionError("not called for missing container")

    def start_container(self, container_name):
        raise AssertionError("not called")


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
