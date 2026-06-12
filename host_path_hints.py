"""Extract host path hints from tool arguments."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


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
        if text.startswith("/"):
            hints.append(text)
        return
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("/"):
            hints.append(text)
        hints.extend(match.group(0).replace("\\ ", " ") for match in HOST_PATH_RE.finditer(value))
        return
    if isinstance(value, Mapping):
        for nested in value.values():
            _collect_host_path_hints(nested, hints)
        return
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        for nested in value:
            _collect_host_path_hints(nested, hints)


def _dedupe(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped
