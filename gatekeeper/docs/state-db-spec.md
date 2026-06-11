# State DB Spec

Default path:

```text
~/.hermes/plugins/docker_runtime/state.db
```

Tables:

- `project_bindings`: trusted local `project_id -> container_name -> host_workspace` index.
- `session_workspace_aliases`: temporary `session_id -> project_id` alias.
- `tool_logs`: audit previews for Docker tool calls.

The DB is a local trusted index, but container use still requires Docker inspect label and mount validation.
