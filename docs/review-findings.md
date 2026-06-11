# Gatekeeper Review Findings

Date: 2026-06-11

Purpose: intermediate handoff document for fixing review findings with the flow:

```text
define test -> confirm test covers issue -> fix issue -> run tests
```

## Summary

Status: all documented review findings are fixed and covered by tests.

Final verification:

```text
pytest tests
21 passed
```

Red-light confirmation was performed before fixes with:

```text
pytest tests/test_fs_ops.py tests/test_runtime_resolver.py tests/test_path_mapper.py tests/test_workspace_commands.py
6 failed, 9 passed
```

The failures matched the review items: missing `docker_terminal` import, lost runtime `session_id`, missing `default` alias fallback, incomplete `.hermes` protection, and ambiguous imported-config workspace messages.

## Finding 1: Slash command session alias may use global `default`

Severity: High

Files:

- `workspace_commands.py`
- `runtime_resolver.py`
- `tests/test_runtime_resolver.py`
- `tests/test_workspace_commands.py`

Original problem:

Hermes slash command handlers may not receive `session_id`. In that path, `/workspace set <path>` stores the alias under `default`, while later tool calls may resolve using a concrete session ID and fail to find the binding.

Test plan:

- Simulate `/workspace set` without session context and assert the `default` alias is created.
- Simulate a later runtime lookup with a non-default `session_id` and only a `default` alias.
- Confirm session-specific aliases still take precedence over the fallback.

Red-light result:

- `test_resolve_runtime_falls_back_to_default_alias` failed with `WorkspaceNotSet`.

Fix:

- `resolve_runtime()` now falls back to the `default` alias only when the concrete session has no binding.
- Session-specific aliases continue to win when present.

Status: Fixed.

## Finding 2: `docker_list_files` fails at runtime with `NameError`

Severity: High

Files:

- `fs_ops.py`
- `tests/test_fs_ops.py`

Original problem:

`list_files()` called `docker_terminal(...)` without importing it.

Test plan:

- Add `test_list_files_uses_terminal_operation`.
- Monkeypatch `fs_ops.docker_terminal` and assert `list_files()` delegates to it with the active runtime.

Red-light result:

- Test setup failed because `gatekeeper.fs_ops` had no `docker_terminal` attribute.

Fix:

- Imported `docker_terminal` from `terminal_ops` in `fs_ops.py`.

Status: Fixed.

## Finding 3: Tool logs lose session ID

Severity: Medium

Files:

- `runtime_resolver.py`
- `tests/test_runtime_resolver.py`

Original problem:

`resolve_runtime()` obtained `session_id`, but `runtime_from_binding()` returned `DockerRuntime(session_id="", ...)`. Tool logs written later by `docker_terminal()` could not record the actual session.

Test plan:

- Create a project binding and session alias.
- Resolve runtime with `session_id="s1"`.
- Assert `DockerRuntime.session_id == "s1"`.

Red-light result:

- `test_resolve_runtime_preserves_session_id` failed because the runtime session ID was empty.

Fix:

- `resolve_runtime()` now passes `session_id` into `runtime_from_binding()`.
- `runtime_from_binding()` accepts the session ID and stores it on `DockerRuntime`.

Status: Fixed.

## Finding 4: Foreign config import/adopt/recreate paths are incomplete

Severity: Medium

Files:

- `workspace_commands.py`
- `tests/test_workspace_commands.py`

Original problem:

When `.hermes/docker-runtime.json` existed but local `state.db` had no binding, `workspace_set()` performed mostly correct operations but user-facing output did not distinguish imported config flows:

- config exists + missing state + missing container -> recreate locally
- config exists + missing state + valid container -> adopt
- label mismatch -> reject
- mount mismatch -> reject and suggest recreate

Test plan:

- Existing config + missing state.db + missing container.
- Existing config + missing state.db + matching stopped container.
- Existing config + label mismatch.
- Existing config + mount mismatch.

Red-light result:

- Import/recreate and import/adopt tests failed because output said only `loaded project config` and generic `created/reused existing Docker container`.
- Reject paths already behaved correctly and are now explicitly covered.

Fix:

- `workspace_set()` now detects an imported config when config exists but no local project binding exists.
- Imported missing-container path reports `imported project config` and `recreated missing Docker container from imported project config`.
- Imported valid-container path reports `imported project config` and `adopted existing Docker container from imported project config`.
- Known project config path now reports `loaded known project config`.

Status: Fixed.

## Finding 5: Protected path policy only blocks one file

Severity: Medium

Files:

- `path_mapper.py`
- `tests/test_path_mapper.py`

Original problem:

`PathMapper.assert_writable()` blocked only `/workspace/.hermes/docker-runtime.json`, permitting file tools to write other metadata under `/workspace/.hermes/`.

Test plan:

- Add a test that attempts to write `/workspace/.hermes/other.json`.
- Choose the stricter expected behavior: reject all writes under `/workspace/.hermes`.

Red-light result:

- `test_path_mapper_protects_all_hermes_metadata` failed because no exception was raised.

Fix:

- `PathMapper.assert_writable()` now rejects writes to `/workspace/.hermes` and all descendants.

Status: Fixed.

## Remaining Notes

- `gatekeeper.zip` is still untracked in the repository root and was not changed.
- Docker integration was not run because previous local verification showed Docker was unavailable on this machine.
- The plugin root is now the repository root: `/Users/foxseventeen/code/gatekeeper`.
