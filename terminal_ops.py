"""Docker-backed terminal operation."""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import asdict, dataclass

from .config import CONTAINER_WORKSPACE, DEFAULT_SETTINGS, DockerRuntimeSettings
from .runtime_resolver import DockerRuntime
from .state_store import StateStore


logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int
    duration_ms: int


def docker_terminal(
    command: str,
    runtime: DockerRuntime,
    *,
    timeout: int | None = None,
    settings: DockerRuntimeSettings = DEFAULT_SETTINGS,
    store: StateStore | None = None,
) -> CommandResult:
    start = time.time()
    cmd = [
        settings.docker_bin,
        "exec",
        "-w",
        CONTAINER_WORKSPACE,
        runtime.container_name,
        "bash",
        "-lc",
        command,
    ]
    logger.info(
        "Gatekeeper docker_terminal 命令开始：session_id=%s project_id=%s container_name=%s cmd=%r timeout=%s",
        runtime.session_id,
        runtime.project_id,
        runtime.container_name,
        cmd,
        timeout or settings.command_timeout_seconds,
    )
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout or settings.command_timeout_seconds,
        check=False,
    )
    duration_ms = int((time.time() - start) * 1000)
    logger.info(
        "Gatekeeper docker_terminal 命令结束：container_name=%s returncode=%s duration_ms=%s stdout=%r stderr=%r",
        runtime.container_name,
        proc.returncode,
        duration_ms,
        (proc.stdout or "").strip(),
        (proc.stderr or "").strip(),
    )
    result = CommandResult(proc.stdout, proc.stderr, proc.returncode, duration_ms)
    if store:
        store.insert_tool_log(
            "docker_terminal",
            {"command": command},
            project_id=runtime.project_id,
            session_id=runtime.session_id,
            ok=proc.returncode == 0,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_ms=duration_ms,
        )
    return result


def result_to_dict(result: CommandResult) -> dict:
    return asdict(result)
