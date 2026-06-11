from pathlib import Path

import pytest

from gatekeeper.config import DockerRuntimeSettings
from gatekeeper.errors import WorkspacePolicyError
from gatekeeper.workspace_policy import validate_host_workspace


def test_validate_host_workspace_allows_tmp_project(tmp_path: Path):
    settings = DockerRuntimeSettings(deny_roots=(Path("/etc"),))
    assert validate_host_workspace(tmp_path, settings) == tmp_path.resolve()


def test_validate_host_workspace_rejects_relative():
    with pytest.raises(WorkspacePolicyError):
        validate_host_workspace("relative/path")
