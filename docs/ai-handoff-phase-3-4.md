# AI Handoff: Phase 3-4 Docker Runtime Tools

Status: implemented with local Docker unavailable.

Completed:

- Implemented `runtime_resolver.py` to resolve session alias -> project binding -> validated Docker runtime.
- Implemented `path_mapper.py`; structured path args map to `/workspace`, reject traversal and outside-workspace absolute paths.
- Implemented protected path check for `/workspace/.hermes/docker-runtime.json` writes/patches.
- Implemented `terminal_ops.py` using `docker exec -w /workspace <container> bash -lc <command>` without command path rewriting.
- Implemented `fs_ops.py` and `search_ops.py` over Docker terminal execution.

Known limitations:

- File write/patch helpers currently embed JSON payloads into the Python script passed to `bash -lc`; acceptable for MVP tests but should be hardened to stdin transport before production.
- `list_files` uses a simple shell pipeline and should eventually avoid shell composition.
- Real Docker execution was not verified because local Docker is missing.

Next AI should continue with Phase 5:

- Register tools, hooks, plugin manifest, Dockerfile.
- Add focused unit tests and a test report.
