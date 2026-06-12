from pathlib import Path

from gatekeeper.host_path_hints import extract_host_path_hints


def test_extract_host_path_hints_ignores_container_workspace_paths():
    hints = extract_host_path_hints("g++ /workspace/src/main.cpp -o /workspace/build/main")

    assert hints == []


def test_extract_host_path_hints_keeps_real_host_paths(tmp_path: Path):
    source = tmp_path / "src" / "main.cpp"

    hints = extract_host_path_hints(f"g++ {source} -o /workspace/build/main")

    assert hints == [str(source)]
