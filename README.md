# Gatekeeper

Gatekeeper 是一个 Hermes 插件，用来把每个项目工作区绑定到一个专属 Docker 容器中。用户执行 `/workspace set <绝对路径>` 后，插件会把后续的终端、文件、搜索等工具调用解析到这个受信任的项目容器里。

## 目录结构

当前目录就是插件根目录。使用时，把整个 `gatekeeper` 目录复制或软链接到 Hermes 的 `plugins/` 目录中，然后启用 `gatekeeper` 插件即可。

主要文件：

- `plugin.yaml`：Hermes 插件元数据。
- `__init__.py`：插件注册入口。
- `workspace_commands.py`：`/workspace ...` 斜杠命令实现。
- `tools.py`：Docker 运行时工具处理器。
- `hooks.py`：原生工具拦截和 Docker 上下文注入。
- `docs/`：实现说明、阶段交接文档和 review 修复记录。
- `tests/`：单元测试。

## 使用方式

显式绑定一个工作区：

```text
/workspace set /absolute/path/to/project
```

查看或重置当前绑定：

```text
/workspace status
/workspace reset
```

修复或重建项目容器：

```text
/workspace repair
/workspace recreate
```

项目会被挂载到容器内的 `/workspace`。普通文件工具不能写入 `/workspace/.hermes`，这样可以避免插件元数据被工作区文件操作误改。

`/workspace set` 会把用户传入的路径视为 Docker daemon 所在宿主机上的路径，并通过一次只读 bind mount probe 验证 Docker 是否能看到该目录。因此，如果 Hermes agent 自身运行在容器中，需要确保它能访问 Docker CLI 和 Docker socket。

## 开发

在当前目录运行单元测试：

```bash
pytest tests
```

运行 Python 编译检查：

```bash
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall .
```

在已安装 Docker 的机器上构建运行时镜像：

```bash
docker build -t hermes-docker-runtime:latest .
```

最近一次本地验证没有运行 Docker 集成测试，因为当前机器上没有可用的 Docker CLI。
