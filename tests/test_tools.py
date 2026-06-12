import json
from pathlib import Path

from gatekeeper import tools
from gatekeeper.config import DockerRuntimeSettings
from gatekeeper.state_store import StateStore
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


def test_docker_terminal_handler_auto_binds_and_rewrites_host_paths(monkeypatch, tmp_path: Path):
    project = tmp_path / "project"
    source = project / "src" / "main.cpp"
    output = project / "build" / "main"
    source.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
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
