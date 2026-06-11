# Project Config Spec

Path:

```text
<host_workspace>/.hermes/docker-runtime.json
```

Required fields:

- `schema_version`
- `project_id`
- `container_name`
- `image`
- `container_workspace`
- `logical_workspace`
- `created_at`
- `updated_at`
- `created_by`
- `binding_mode`
- `host_workspace_hint`

The config is discoverable and portable, but not trusted by itself. Runtime use requires state.db and Docker label/mount validation.
