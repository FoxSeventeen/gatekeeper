from pathlib import Path

from gatekeeper import fs_ops
from gatekeeper.path_mapper import PathMapper
from gatekeeper.runtime_resolver import DockerRuntime


def test_list_files_uses_terminal_operation(monkeypatch, tmp_path: Path):
    runtime = DockerRuntime(
        session_id="s1",
        project_id="proj_123456789abc",
        container_name="hermes-runtime-123456789abc",
        host_workspace=tmp_path,
    )
    mapper = PathMapper(tmp_path)
    calls = []

    class Result:
        def __init__(self):
            self.stdout = "/workspace/a.py\n"
            self.stderr = ""
            self.returncode = 0
            self.duration_ms = 3

    def fake_docker_terminal(command, passed_runtime):
        calls.append((command, passed_runtime))
        return Result()

    monkeypatch.setattr(fs_ops, "docker_terminal", fake_docker_terminal)

    result = fs_ops.list_files("/workspace", runtime, mapper)

    assert result["path"] == "/workspace"
    assert result["stdout"] == "/workspace/a.py\n"
    assert calls[0][1] is runtime
