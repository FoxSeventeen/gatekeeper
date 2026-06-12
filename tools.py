"""Hermes tool handlers exposed to the agent."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .errors import DockerRuntimeError
from .fs_ops import list_files, patch_file, read_file, write_file
from .host_path_hints import extract_host_path_hints
from .path_mapper import PathMapper
from .runtime_resolver import resolve_runtime
from .search_ops import search_files
from .state_store import StateStore
from .terminal_ops import docker_terminal, result_to_dict
from .workspace_commands import handle_workspace_command


logger = logging.getLogger(__name__)


def _json_response(tool_name: str, fn: Callable[[], dict]) -> str:
    try:
        payload = {"ok": True, **fn()}
        logger.info("Gatekeeper 工具调用完成：tool=%s ok=True response_keys=%s", tool_name, sorted(payload.keys()))
        return json.dumps(payload, ensure_ascii=False)
    except DockerRuntimeError as exc:
        logger.info("Gatekeeper 工具调用失败：tool=%s error=%s", tool_name, exc)
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    except Exception as exc:
        logger.info("Gatekeeper 工具调用异常：tool=%s exception_type=%s error=%s", tool_name, type(exc).__name__, exc)
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)


def _runtime_and_mapper(context: dict, args: dict[str, Any] | None = None):
    candidate_paths = extract_host_path_hints(args or {})
    logger.info(
        "Gatekeeper 工具运行时解析开始：context_keys=%s candidate_paths=%s",
        sorted(context.keys()),
        candidate_paths,
    )
    runtime = resolve_runtime(candidate_paths=candidate_paths, allow_auto_bind=True, **context)
    logger.info(
        "Gatekeeper 工具运行时解析完成：session_id=%s project_id=%s container_name=%s host_workspace=%s container_workspace=%s",
        runtime.session_id,
        runtime.project_id,
        runtime.container_name,
        runtime.host_workspace,
        runtime.container_workspace,
    )
    mapper = PathMapper(runtime.host_workspace, runtime.container_workspace)
    return runtime, mapper


def docker_terminal_handler(args: dict[str, Any], **kwargs) -> str:
    logger.info("Gatekeeper 工具调用开始：tool=docker_terminal args=%r context_keys=%s", args, sorted(kwargs.keys()))

    def run() -> dict:
        command = str(args.get("command", ""))
        candidate_paths = extract_host_path_hints(command)
        runtime = resolve_runtime(candidate_paths=candidate_paths, allow_auto_bind=True, **kwargs)
        mapper = PathMapper(runtime.host_workspace, runtime.container_workspace)
        mapped_command = _rewrite_host_paths(command, mapper, candidate_paths)
        logger.info(
            "Gatekeeper docker_terminal 解析完成：session_id=%s project_id=%s container_name=%s original_command=%r mapped_command=%r candidate_paths=%s",
            runtime.session_id,
            runtime.project_id,
            runtime.container_name,
            command,
            mapped_command,
            candidate_paths,
        )
        result = docker_terminal(mapped_command, runtime)
        return result_to_dict(result)

    return _json_response("docker_terminal", run)


def docker_read_file_handler(args: dict[str, Any], **kwargs) -> str:
    logger.info("Gatekeeper 工具调用开始：tool=docker_read_file args=%r context_keys=%s", args, sorted(kwargs.keys()))
    return _json_response("docker_read_file", lambda: read_file(str(args.get("path", "")), *_runtime_and_mapper(kwargs, args)))


def docker_write_file_handler(args: dict[str, Any], **kwargs) -> str:
    logger.info(
        "Gatekeeper 工具调用开始：tool=docker_write_file path=%r content_length=%s context_keys=%s",
        args.get("path", ""),
        len(str(args.get("content", ""))),
        sorted(kwargs.keys()),
    )

    def run() -> dict:
        runtime, mapper = _runtime_and_mapper(kwargs, args)
        return write_file(str(args.get("path", "")), str(args.get("content", "")), runtime, mapper)

    return _json_response("docker_write_file", run)


def docker_patch_handler(args: dict[str, Any], **kwargs) -> str:
    logger.info(
        "Gatekeeper 工具调用开始：tool=docker_patch path=%r old_length=%s new_length=%s context_keys=%s",
        args.get("path", ""),
        len(str(args.get("old", ""))),
        len(str(args.get("new", ""))),
        sorted(kwargs.keys()),
    )

    def run() -> dict:
        runtime, mapper = _runtime_and_mapper(kwargs, args)
        return patch_file(
            str(args.get("path", "")),
            str(args.get("old", "")),
            str(args.get("new", "")),
            runtime,
            mapper,
        )

    return _json_response("docker_patch", run)


def docker_list_files_handler(args: dict[str, Any], **kwargs) -> str:
    logger.info("Gatekeeper 工具调用开始：tool=docker_list_files args=%r context_keys=%s", args, sorted(kwargs.keys()))

    def run() -> dict:
        runtime, mapper = _runtime_and_mapper(kwargs, args)
        return list_files(str(args.get("path", "/workspace")), runtime, mapper)

    return _json_response("docker_list_files", run)


def docker_search_files_handler(args: dict[str, Any], **kwargs) -> str:
    logger.info("Gatekeeper 工具调用开始：tool=docker_search_files args=%r context_keys=%s", args, sorted(kwargs.keys()))

    def run() -> dict:
        runtime, mapper = _runtime_and_mapper(kwargs, args)
        return search_files(
            str(args.get("path", "/workspace")),
            str(args.get("query", "")),
            runtime,
            mapper,
        )

    return _json_response("docker_search_files", run)


def docker_runtime_status_handler(args: dict[str, Any], **kwargs) -> str:
    logger.info("Gatekeeper 工具调用开始：tool=docker_runtime_status args=%r context_keys=%s", args, sorted(kwargs.keys()))
    return json.dumps(
        {
            "ok": True,
            "status": handle_workspace_command("status", **kwargs),
        },
        ensure_ascii=False,
    )


def _rewrite_host_paths(command: str, mapper: PathMapper, candidate_paths: list[str]) -> str:
    rewritten = command
    for raw_path in sorted(candidate_paths, key=len, reverse=True):
        try:
            container_path = mapper.to_container(raw_path)
        except DockerRuntimeError:
            continue
        if container_path != raw_path:
            rewritten = rewritten.replace(raw_path, container_path)
    return rewritten


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
