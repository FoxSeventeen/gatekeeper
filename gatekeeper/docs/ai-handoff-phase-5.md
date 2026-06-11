# AI Handoff: Phase 5 Hooks And Registration

Status: complete for MVP.

Completed:

- Added `tools.py` with Hermes JSON-returning handlers for Docker terminal, file, search, list, and status.
- Added `hooks.py` with `pre_llm_call` context injection and `pre_tool_call` allowlist/blocklist enforcement.
- Added plugin registration in `__init__.py`.
- Added `plugin.yaml`.
- Added `Dockerfile`.
- Added command/state/project spec docs.

Known limitations:

- Unknown tools are denied by default, which is intentionally strict and may need deployment-specific allowlist expansion.
- Hook runtime resolution creates a default `StateStore`; tests should set `HERMES_HOME` or inject lower-level components where possible.

Next AI should continue with tests and final report.
