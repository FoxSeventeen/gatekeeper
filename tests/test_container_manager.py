from pathlib import Path
from subprocess import CompletedProcess

from gatekeeper.config import CONTAINER_WORKSPACE, DockerRuntimeSettings
from gatekeeper.container_manager import ContainerManager
from gatekeeper.project_config import create_project_config


class RecordingContainerManager(ContainerManager):
    def __init__(self, settings):
        super().__init__(settings)
        self.calls = []

    def _run(self, args, *, input_text=None, timeout=None):
        self.calls.append(args)
        return CompletedProcess(args, 0, stdout="container-id\n", stderr="")


def test_create_container_uses_strict_bind_mount():
    settings = DockerRuntimeSettings(docker_bin="docker")
    manager = RecordingContainerManager(settings)
    config = create_project_config(Path("/home/zhouzepeng/project1"))

    manager.create_container(config, Path("/home/zhouzepeng/project1"))

    args = manager.calls[0]
    assert "--mount" in args
    assert f"type=bind,source=/home/zhouzepeng/project1,target={CONTAINER_WORKSPACE}" in args
    assert "-v" not in args


def test_validate_container_mount_uses_docker_reported_source_without_local_resolve():
    manager = ContainerManager(DockerRuntimeSettings())
    config = create_project_config(Path("/home/zhouzepeng/project1"))
    info = {
        "Config": {
            "Labels": {
                "hermes.plugin": "docker-runtime",
                "hermes.project_id": config.project_id,
                "hermes.binding_mode": "workspace_config",
                "hermes.container_workspace": CONTAINER_WORKSPACE,
            }
        },
        "State": {"Running": True},
        "Mounts": [
            {
                "Type": "bind",
                "Source": "/home/zhouzepeng/project1",
                "Destination": CONTAINER_WORKSPACE,
            }
        ],
    }

    validation = manager.validate_container_for_project(
        info,
        config,
        Path("/home/zhouzepeng/project1"),
    )

    assert validation.ok
    assert validation.mount_source == "/home/zhouzepeng/project1"
