from pathlib import Path

from gatekeeper.project_config import (
    config_path_for_workspace,
    create_project_config,
    read_project_config,
    write_project_config,
)


def test_project_config_round_trip(tmp_path: Path):
    cfg = create_project_config(tmp_path)
    write_project_config(tmp_path, cfg)

    loaded = read_project_config(tmp_path)

    assert loaded == cfg
    assert config_path_for_workspace(tmp_path).exists()
    assert loaded.container_workspace == "/workspace"
