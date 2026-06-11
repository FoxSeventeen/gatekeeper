"""Hermes hooks for Docker workspace context and tool blocking."""

from __future__ import annotations

from .runtime_resolver import resolve_runtime

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
    try:
        runtime = resolve_runtime(**kwargs)
    except Exception:
        return {
            "context": (
                "[docker-runtime]\n"
                "当前会话尚未设置 workspace。\n"
                "请提示用户输入：/workspace set <absolute_host_path>\n"
                "在 workspace 设置前，不要尝试执行 terminal 或文件操作。"
            )
        }
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
    if tool_name in ALLOWED_TOOLS:
        return None
    if tool_name in BLOCKED_TOOLS:
        return {
            "action": "block",
            "message": (
                f"Tool '{tool_name}' is blocked by docker-runtime. "
                "Use docker_* tools inside /workspace instead."
            ),
        }
    return {
        "action": "block",
        "message": f"Tool '{tool_name}' is not in the docker-runtime allowlist.",
    }
