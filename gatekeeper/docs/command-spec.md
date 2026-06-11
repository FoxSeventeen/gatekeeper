# Workspace Command Spec

Registered slash command:

```text
/workspace set <absolute_host_path>
/workspace status
/workspace reset
/workspace recreate
/workspace repair
/workspace fork
/workspace help
```

`/workspace set` is the only workspace binding entry point. Agent-visible tools do not expose workspace setters.

Session IDs are aliases to `project_id`; container binding is keyed by `project_id`.
