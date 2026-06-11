"""Search operations inside the Docker workspace."""

from __future__ import annotations

import shlex

from .path_mapper import PathMapper
from .runtime_resolver import DockerRuntime
from .terminal_ops import docker_terminal


def search_files(path: str, query: str, runtime: DockerRuntime, mapper: PathMapper) -> dict:
    if not query:
        raise ValueError("query may not be empty")
    container_path = mapper.to_container(path or "/workspace")
    quoted_query = shlex.quote(query)
    quoted_path = shlex.quote(container_path)
    command = (
        f"if command -v rg >/dev/null 2>&1; then "
        f"rg --line-number --no-heading {quoted_query} {quoted_path}; "
        f"else python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"root = Path({container_path!r})\n"
        f"needle = {query!r}\n"
        "for p in root.rglob('*'):\n"
        "    if p.is_file():\n"
        "        try:\n"
        "            for i, line in enumerate(p.read_text(encoding='utf-8', errors='ignore').splitlines(), 1):\n"
        "                if needle in line:\n"
        "                    print(f'{p}:{i}:{line}')\n"
        "        except OSError:\n"
        "            pass\n"
        "PY\n"
        "fi"
    )
    result = docker_terminal(command, runtime)
    return {"path": container_path, "query": query, **result.__dict__}
