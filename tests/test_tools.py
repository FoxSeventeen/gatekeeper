import json
import time
from pathlib import Path

from gatekeeper import tools
from gatekeeper.config import DockerRuntimeSettings
from gatekeeper.project_config import create_project_config, write_project_config
from gatekeeper.state_store import ProjectBinding, StateStore
from gatekeeper.terminal_ops import CommandResult


class AutoBindContainers:
    def __init__(self):
        self.created = []

    def inspect_container(self, container_name):
        return None

    def create_container(self, config, host_workspace):
        self.created.append((config.container_name, str(host_workspace)))

    def ensure_container_for_binding(self, binding, config):
        return None


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


def test_docker_terminal_handler_rewrites_host_paths_after_workspace_set(monkeypatch, tmp_path: Path):
    project = tmp_path / "project"
    source = project / "src" / "main.cpp"
    output = project / "build" / "main"
    source.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    source.write_text("int main() { return 0; }\n", encoding="utf-8")
    store = StateStore(tmp_path / "state.db")
    containers = AutoBindContainers()
    project_id = _insert_binding(store, project)
    store.upsert_session_alias("s1", None, project_id)
    settings = DockerRuntimeSettings(
        state_db_path=tmp_path / "state.db",
        deny_roots=(Path("/etc"),),
        docker_probe_enabled=False,
    )
    calls = []

    def fake_docker_terminal(command, runtime):
        calls.append((command, runtime))
        return CommandResult(stdout="", stderr="", returncode=0, duration_ms=1)

    monkeypatch.setattr(tools, "docker_terminal", fake_docker_terminal)

    payload = json.loads(
        tools.docker_terminal_handler(
            {"command": f"g++ {source} -o {output}"},
            session_id="s1",
            cwd=str(project),
            store=store,
            containers=containers,
            settings=settings,
        )
    )

    assert payload["ok"] is True
    assert calls[0][0] == "g++ /workspace/src/main.cpp -o /workspace/build/main"
    assert calls[0][1].host_workspace == project.resolve()
    assert store.get_project_id_for_session("s1") == calls[0][1].project_id
    assert containers.created == []


def test_docker_terminal_requires_workspace_set_even_with_host_path(monkeypatch, tmp_path: Path):
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
    calls = []

    def fake_docker_terminal(command, runtime):
        calls.append((command, runtime))
        return CommandResult(stdout="", stderr="", returncode=0, duration_ms=1)

    monkeypatch.setattr(tools, "docker_terminal", fake_docker_terminal)

    payload = json.loads(
        tools.docker_terminal_handler(
            {"command": f"g++ {source}"},
            session_id="s1",
            cwd=str(project),
            store=store,
            containers=containers,
            settings=settings,
        )
    )

    assert payload["ok"] is False
    assert "/workspace set" in payload["error"]
    assert calls == []
    assert containers.created == []
