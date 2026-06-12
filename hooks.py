"""Hermes hooks for Docker workspace context and tool blocking."""

from __future__ import annotations

import logging

from .runtime_resolver import resolve_runtime


logger = logging.getLogger(__name__)

ALLOWED_TOOLS = {
    "docker_terminal",
    "docker_read_file",
    "docker_write_file",
    "docker_patch",
    "docker_search_files",
    "docker_list_files",
    "docker_runtime_status",
    "clarify",
    "todo",
}

BLOCKED_TOOLS = {
    "terminal",
    "process",
    "read_file",
    "write_file",
    "patch",
    "search_files",
    "list_files",
    "execute_code",
    "delegate_task",
    "cronjob",
    "skill_manage",
    "set_workspace",
    "request_workspace",
    "find_workspaces",
    "change_workspace",
    "select_workspace",
}


def inject_docker_context(**kwargs):
    logger.info("Gatekeeper hook pre_llm_call 开始：注入 Docker 上下文 context_keys=%s", sorted(kwargs.keys()))
    try:
        runtime = resolve_runtime(**kwargs)
    except Exception as exc:
        logger.info("Gatekeeper hook pre_llm_call：当前无可用 workspace，注入未绑定提示 error=%s", exc)
        return {
            "context": (
                "[docker-runtime]\n"
                "当前会话尚未设置 workspace。\n"
                "请提示用户输入：/workspace set <absolute_host_path>\n"
                "在 workspace 设置前，不要尝试调用 docker_terminal 或 docker 文件工具执行 terminal、文件读写、搜索等操作。"
            )
        }
    logger.info(
        "Gatekeeper hook pre_llm_call：注入已绑定 Docker 上下文 session_id=%s project_id=%s container_name=%s host_workspace=%s",
        runtime.session_id,
        runtime.project_id,
        runtime.container_name,
        runtime.host_workspace,
    )
    return {
        "context": (
            "[docker-runtime]\n"
            "当前会话使用 Docker Workspace Runtime。\n"
            "项目根目录是 /workspace。\n"
            "所有 shell 命令必须使用 docker_terminal。\n"
            "文件读取、写入、修改、搜索必须使用 docker_read_file/docker_write_file/docker_patch/docker_search_files。\n"
            "不要使用 host 绝对路径。\n"
            "workspace 只能由用户 slash command /workspace set 设置，agent 不能修改。\n"
            f"project_id={runtime.project_id} container={runtime.container_name}"
        )
    }


def block_native_tools(tool_name: str, args: dict | None = None, **kwargs):
    logger.info(
        "Gatekeeper hook pre_tool_call 开始：tool_name=%s args=%r context_keys=%s",
        tool_name,
        args,
        sorted(kwargs.keys()),
    )
    if tool_name in ALLOWED_TOOLS:
        logger.info("Gatekeeper hook pre_tool_call 放行：tool_name=%s", tool_name)
        return None
    if tool_name in BLOCKED_TOOLS:
        logger.info("Gatekeeper hook pre_tool_call 拦截原生工具：tool_name=%s args=%r", tool_name, args)
        return {
            "action": "block",
            "message": (
                f"Tool '{tool_name}' is blocked by docker-runtime. "
                "Use docker_* tools inside /workspace instead."
            ),
        }
    logger.info("Gatekeeper hook pre_tool_call 拦截非 allowlist 工具：tool_name=%s args=%r", tool_name, args)
    return {
        "action": "block",
        "message": f"Tool '{tool_name}' is not in the docker-runtime allowlist.",
    }
