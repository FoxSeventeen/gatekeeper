from pathlib import Path

import pytest

from gatekeeper.errors import ProtectedPathError, WorkspacePolicyError
from gatekeeper.path_mapper import PathMapper


def test_path_mapper_maps_relative_and_container_paths(tmp_path: Path):
    mapper = PathMapper(tmp_path)
    assert mapper.to_container("src/a.py") == "/workspace/src/a.py"
    assert mapper.to_container("/workspace/src/a.py") == "/workspace/src/a.py"


def test_path_mapper_rejects_traversal(tmp_path: Path):
    mapper = PathMapper(tmp_path)
    with pytest.raises(WorkspacePolicyError):
        mapper.to_container("../outside")


def test_path_mapper_protects_project_config(tmp_path: Path):
    mapper = PathMapper(tmp_path)
    with pytest.raises(ProtectedPathError):
        mapper.assert_writable("/workspace/.hermes/docker-runtime.json")
