"""Hermes tool handlers exposed to the agent."""

from __future__ import annotations

import json
from typing import Any, Callable

from .errors import DockerRuntimeError
from .fs_ops import list_files, patch_file, read_file, write_file
from .path_mapper import PathMapper
from .runtime_resolver import resolve_runtime
from .search_ops import search_files
from .state_store import StateStore
from .terminal_ops import docker_terminal, result_to_dict
from .workspace_commands import handle_workspace_command


def _json_response(fn: Callable[[], dict]) -> str:
    try:
        return json.dumps({"ok": True, **fn()}, ensure_ascii=False)
    except DockerRuntimeError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)


def _runtime_and_mapper(context: dict):
    runtime = resolve_runtime(**context)
    mapper = PathMapper(runtime.host_workspace, runtime.container_workspace)
    return runtime, mapper


def docker_terminal_handler(args: dict[str, Any], **kwargs) -> str:
    def run() -> dict:
        runtime = resolve_runtime(**kwargs)
        result = docker_terminal(str(args.get("command", "")), runtime)
        return result_to_dict(result)

    return _json_response(run)


def docker_read_file_handler(args: dict[str, Any], **kwargs) -> str:
    return _json_response(lambda: read_file(str(args.get("path", "")), *_runtime_and_mapper(kwargs)))


def docker_write_file_handler(args: dict[str, Any], **kwargs) -> str:
    def run() -> dict:
        runtime, mapper = _runtime_and_mapper(kwargs)
        return write_file(str(args.get("path", "")), str(args.get("content", "")), runtime, mapper)

    return _json_response(run)


def docker_patch_handler(args: dict[str, Any], **kwargs) -> str:
    def run() -> dict:
        runtime, mapper = _runtime_and_mapper(kwargs)
        return patch_file(
            str(args.get("path", "")),
            str(args.get("old", "")),
            str(args.get("new", "")),
            runtime,
            mapper,
        )

    return _json_response(run)


def docker_list_files_handler(args: dict[str, Any], **kwargs) -> str:
    def run() -> dict:
        runtime, mapper = _runtime_and_mapper(kwargs)
        return list_files(str(args.get("path", "/workspace")), runtime, mapper)

    return _json_response(run)


def docker_search_files_handler(args: dict[str, Any], **kwargs) -> str:
    def run() -> dict:
        runtime, mapper = _runtime_and_mapper(kwargs)
        return search_files(
            str(args.get("path", "/workspace")),
            str(args.get("query", "")),
            runtime,
            mapper,
        )

    return _json_response(run)


def docker_runtime_status_handler(args: dict[str, Any], **kwargs) -> str:
    return json.dumps(
        {
            "ok": True,
            "status": handle_workspace_command("status", **kwargs),
        },
        ensure_ascii=False,
    )


TOOL_DEFS = [
    (
        "docker_terminal",
        "Run a shell command inside the bound Docker container at /workspace.",
        {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
        docker_terminal_handler,
    ),
    (
        "docker_read_file",
        "Read a UTF-8 file inside /workspace.",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        docker_read_file_handler,
    ),
    (
        "docker_write_file",
        "Write a UTF-8 file inside /workspace.",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
        docker_write_file_handler,
    ),
    (
        "docker_patch",
        "Replace the first occurrence of text in a file inside /workspace.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string"},
                "new": {"type": "string"},
            },
            "required": ["path", "old", "new"],
        },
        docker_patch_handler,
    ),
    (
        "docker_list_files",
        "List files under a /workspace path.",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        docker_list_files_handler,
    ),
    (
        "docker_search_files",
        "Search text under a /workspace path.",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}, "query": {"type": "string"}},
            "required": ["query"],
        },
        docker_search_files_handler,
    ),
    (
        "docker_runtime_status",
        "Show the current Docker workspace runtime status.",
        {"type": "object", "properties": {}},
        docker_runtime_status_handler,
    ),
]
