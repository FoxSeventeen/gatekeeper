"""Hermes project-centric Docker runtime plugin."""

from __future__ import annotations

from .hooks import block_native_tools, inject_docker_context
from .tools import TOOL_DEFS
from .workspace_commands import handle_workspace_command


def register(ctx):
    for name, description, schema, handler in TOOL_DEFS:
        ctx.register_tool(
            name=name,
            toolset="docker_runtime",
            schema=schema,
            handler=handler,
            description=description,
        )

    ctx.register_hook("pre_llm_call", inject_docker_context)
    ctx.register_hook("pre_tool_call", block_native_tools)
    ctx.register_command(
        "workspace",
        handler=handle_workspace_command,
        description="Manage project-centric Docker workspace binding",
        args_hint="set <path> | status | reset | recreate | repair | fork | help",
    )
