from pathlib import Path

import pytest

from gatekeeper.config import DockerRuntimeSettings
from gatekeeper.errors import WorkspacePolicyError
from gatekeeper.workspace_policy import (
    WorkspaceDockerProbeError,
    validate_host_workspace,
)


def test_validate_host_workspace_allows_tmp_project(tmp_path: Path):
    settings = DockerRuntimeSettings(deny_roots=(Path("/etc"),), docker_probe_enabled=False)
    assert validate_host_workspace(tmp_path, settings) == tmp_path.resolve()


def test_validate_host_workspace_rejects_relative():
    with pytest.raises(WorkspacePolicyError):
        validate_host_workspace("relative/path")


def test_validate_host_workspace_uses_docker_probe_not_path_exists(monkeypatch):
    calls = []

    def probe(host_path, *, settings):
        calls.append((host_path, settings.probe_image))

    monkeypatch.setattr("gatekeeper.workspace_policy.validate_workspace_visible_to_docker", probe)
    settings = DockerRuntimeSettings(deny_roots=(Path("/etc"),))

    workspace = validate_host_workspace("/home/zhouzepeng/project1", settings)

    assert workspace == Path("/home/zhouzepeng/project1")
    assert calls == [("/home/zhouzepeng/project1", settings.probe_image)]


def test_validate_host_workspace_reports_probe_failure(monkeypatch):
    def probe(host_path, *, settings):
        raise WorkspaceDockerProbeError("not visible to docker")

    monkeypatch.setattr("gatekeeper.workspace_policy.validate_workspace_visible_to_docker", probe)
    settings = DockerRuntimeSettings(deny_roots=(Path("/etc"),))

    with pytest.raises(WorkspaceDockerProbeError, match="not visible"):
        validate_host_workspace("/home/zhouzepeng/project1", settings)
