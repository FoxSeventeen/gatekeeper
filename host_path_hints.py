"""Extract host path hints from tool arguments."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .config import CONTAINER_WORKSPACE


HOST_PATH_RE = re.compile(r"(?<![\w.-])/(?:[^\s'\"`;|&<>$(){}\\]|\\.)+")


def extract_host_path_hints(value: Any) -> list[str]:
    hints: list[str] = []
    _collect_host_path_hints(value, hints)
    return _dedupe(hints)


def _collect_host_path_hints(value: Any, hints: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, Path):
        text = str(value)
        if _is_host_path_hint(text):
            hints.append(text)
        return
    if isinstance(value, str):
        text = value.strip()
        if _is_host_path_hint(text):
            hints.append(text)
        hints.extend(
            path
            for path in (match.group(0).replace("\\ ", " ") for match in HOST_PATH_RE.finditer(value))
            if _is_host_path_hint(path)
        )
        return
    if isinstance(value, Mapping):
        for nested in value.values():
            _collect_host_path_hints(nested, hints)
        return
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        for nested in value:
            _collect_host_path_hints(nested, hints)


def _is_host_path_hint(path: str) -> bool:
    return path.startswith("/") and path != CONTAINER_WORKSPACE and not path.startswith(CONTAINER_WORKSPACE + "/")


def _dedupe(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped
