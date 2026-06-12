"""Small helpers for extracting Hermes session IDs."""

from __future__ import annotations


def session_id_from_context(context: dict) -> str:
    for key in ("session_id", "root_session_id", "parent_session_id", "task_id"):
        value = context.get(key)
        if isinstance(value, str) and value:
            return value
    return "default"


def root_session_id_from_context(context: dict) -> str | None:
    value = context.get("root_session_id") or context.get("parent_session_id")
    return value if isinstance(value, str) and value else None
