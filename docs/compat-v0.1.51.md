# Hermes v0.1.51 Compatibility Notes

Source inspected: local `/Users/foxseventeen/code/hermes-agent`.

Findings:

- `hermes_cli/plugins.py` exposes `PluginContext.register_tool(name, toolset, schema, handler, ...)`.
- `PluginContext.register_hook(hook_name, callback)` accepts `pre_tool_call`, `post_tool_call`, `pre_llm_call`, and others from `VALID_HOOKS`.
- `PluginContext.register_command(name, handler, description="", args_hint="")` exists.
- Slash command handler signature is `fn(raw_args: str) -> str | None`; async handlers are also supported by gateway dispatch.
- `pre_tool_call` may block by returning `{"action": "block", "message": "..."}`.
- `pre_llm_call` may inject per-turn context by returning `{"context": "..."}` or a string.

Compatibility decision:

- Use plugin-level `ctx.register_command("workspace", ...)` for `/workspace`.
- Because command handlers only receive `raw_args`, this MVP accepts optional `session_id` and `root_session_id` through keyword context in direct Python calls, but registered Hermes command usage falls back to a stable local session key named `default`.
- Tool handlers receive `args: dict, **kwargs` and can use `session_id`/`task_id` from Hermes when available.

Docker availability:

- `docker --version` failed locally with `command not found`.
- Docker integration tests were designed for mock/CI execution and are not run on this machine.
