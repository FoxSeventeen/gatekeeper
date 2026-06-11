"""File operations executed inside the Docker workspace."""

from __future__ import annotations

import subprocess

from .config import CONTAINER_WORKSPACE, DEFAULT_SETTINGS, DockerRuntimeSettings
from .path_mapper import PathMapper
from .runtime_resolver import DockerRuntime
from .terminal_ops import docker_terminal


def _python_exec(
    script: str,
    runtime: DockerRuntime,
    *,
    stdin: str = "",
    settings: DockerRuntimeSettings = DEFAULT_SETTINGS,
) -> dict:
    proc = subprocess.run(
        [
            settings.docker_bin,
            "exec",
            "-i",
            "-w",
            CONTAINER_WORKSPACE,
            runtime.container_name,
            "python3",
            "-c",
            script,
        ],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=settings.command_timeout_seconds,
        check=False,
    )
    return {
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
        "duration_ms": None,
    }


def read_file(path: str, runtime: DockerRuntime, mapper: PathMapper) -> dict:
    container_path = mapper.to_container(path)
    # Docker exec argv after `-c` is not available through our helper, so keep
    # the path embedded as a repr-only literal; file content still never enters shell.
    result = _python_exec(
        f"from pathlib import Path\nprint(Path({container_path!r}).read_text(encoding='utf-8'), end='')\n",
        runtime,
    )
    return {"path": container_path, **result}


def write_file(path: str, content: str, runtime: DockerRuntime, mapper: PathMapper) -> dict:
    mapper.assert_writable(path)
    container_path = mapper.to_container(path)
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        f"path = Path({container_path!r})\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        "path.write_text(sys.stdin.read(), encoding='utf-8')\n"
        "print(str(path))\n"
    )
    result = _python_exec(script, runtime, stdin=content)
    return {"path": container_path, **result}


def patch_file(path: str, old: str, new: str, runtime: DockerRuntime, mapper: PathMapper) -> dict:
    mapper.assert_writable(path)
    container_path = mapper.to_container(path)
    payload = old + "\0" + new
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        f"path = Path({container_path!r})\n"
        "old, new = sys.stdin.read().split('\\0', 1)\n"
        "text = path.read_text(encoding='utf-8')\n"
        "if old not in text:\n"
        "    raise SystemExit('old text not found')\n"
        "path.write_text(text.replace(old, new, 1), encoding='utf-8')\n"
        "print(str(path))\n"
    )
    result = _python_exec(script, runtime, stdin=payload)
    return {"path": container_path, **result}


def list_files(path: str, runtime: DockerRuntime, mapper: PathMapper) -> dict:
    container_path = mapper.to_container(path)
    result = docker_terminal(
        f"find {container_path!r} -maxdepth 2 -type f | sed 's#^#/##' | head -200",
        runtime,
    )
    return {"path": container_path, **result.__dict__}
