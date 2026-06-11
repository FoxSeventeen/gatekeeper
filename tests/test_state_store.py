from pathlib import Path

from gatekeeper.state_store import ProjectBinding, StateStore


def test_state_store_binding_alias_and_tool_log(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    binding = ProjectBinding(
        project_id="proj_123456789abc",
        container_name="hermes-runtime-123456789abc",
        image="image",
        host_workspace=str(tmp_path),
        config_path=str(tmp_path / ".hermes/docker-runtime.json"),
        container_workspace="/workspace",
        logical_workspace="/workspace",
        state="active",
        created_at=1.0,
        updated_at=1.0,
        last_used_at=None,
    )

    store.upsert_project_binding(binding)
    store.upsert_session_alias("s1", None, binding.project_id)
    store.insert_tool_log("docker_terminal", {"command": "true"}, ok=True, returncode=0)

    assert store.get_project_binding(binding.project_id).container_name == binding.container_name
    assert store.get_project_id_for_session("s1") == binding.project_id

    store.delete_session_alias("s1")
    assert store.get_project_id_for_session("s1") is None
