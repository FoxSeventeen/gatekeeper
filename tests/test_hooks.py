from gatekeeper.hooks import block_native_tools


def test_blocks_native_terminal():
    result = block_native_tools("terminal")
    assert result["action"] == "block"


def test_allows_docker_terminal():
    assert block_native_tools("docker_terminal") is None
