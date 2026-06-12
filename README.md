# Gatekeeper

Gatekeeper 是一个 Hermes 插件，用来把当前会话绑定到一个项目级 Docker 工作区。用户先执行 `/workspace set <宿主机绝对路径>`，插件随后把终端、文件读写、补丁、搜索等操作放到对应的 Docker 容器内执行，容器内项目根目录固定为 `/workspace`。

## 安装

当前仓库根目录就是插件根目录。使用时，把整个 `gatekeeper` 目录复制或软链接到 Hermes 的 `plugins/` 目录中，然后在 Hermes 中启用 `gatekeeper` 插件。

插件元数据位于 `plugin.yaml`：

- 插件名：`gatekeeper`
- 当前版本：`0.2.0`
- 提供工具：`docker_terminal`、`docker_read_file`、`docker_write_file`、`docker_patch`、`docker_search_files`、`docker_list_files`、`docker_runtime_status`
- 提供命令：`/workspace ...`

## 使用方式

绑定工作区：

```text
/workspace set /absolute/path/to/project
```

查看或清除绑定：

```text
/workspace status
/workspace reset
```

修复、重建或导入项目容器：

```text
/workspace repair
/workspace recreate
/workspace fork <new_host_workspace>
```

工作区绑定后：

- 宿主机路径会被 bind mount 到容器内的 `/workspace`。
- shell 命令应通过 `docker_terminal` 在容器内执行。
- 文件读写、修改和搜索应通过 `docker_read_file`、`docker_write_file`、`docker_patch`、`docker_search_files`、`docker_list_files` 执行。
- 传入工作区内的宿主机绝对路径时，插件会改写为 `/workspace/...`。
- `/workspace/.hermes` 是受保护目录，普通文件工具不能写入，避免误改插件元数据。

在执行 `/workspace set` 之前，docker 系列工具不会自动根据命令参数推断工作区，也不会启动容器。此时工具会返回错误提示，要求用户先执行：

```text
/workspace set <absolute_host_path>
```

## Docker 行为

默认执行容器镜像在 `config.py` 中配置：

```text
hub-dev.hexin.cn:9544/security-baseimages/baseimage_cpp:fst-build
```

`/workspace set` 会把用户输入的路径视为 Docker daemon 所在宿主机上的真实路径，并通过只读 bind mount probe 检查 Docker 是否能看到该目录。如果 Hermes agent 自身运行在容器内，需要同时满足：

- agent 能访问 Docker CLI。
- agent 能访问 Docker socket。
- `/workspace set` 传入的是 Docker daemon 视角下可挂载的宿主机路径。

探测镜像默认是：

```text
gatekeeper-runtime:latest
```

如果本机没有该镜像，可以在插件目录构建：

```bash
docker build -t gatekeeper-runtime:latest .
```

## 状态文件

插件会在 Hermes home 下维护工作区绑定状态：

```text
~/.hermes/plugins/docker_runtime/state.db
```

每个项目目录内也会写入项目配置：

```text
.hermes/docker-runtime.json
```

这些文件用于记录项目 ID、容器名、宿主机工作区路径和镜像信息。

## 日志排查

插件已经在关键路径加入中文 `logging.info` 日志，便于定位问题。重点关注以下日志前缀：

- `Gatekeeper /workspace set`：工作区设置、配置读取、容器创建和 session alias 写入。
- `Gatekeeper Docker 可见性探测`：Docker daemon 是否能挂载用户传入的宿主机路径。
- `Gatekeeper 工具调用`：每次 docker 工具调用的参数、上下文和返回结果。
- `Gatekeeper docker_terminal`：实际进入容器执行的命令。
- `Gatekeeper 容器校验`：容器 label、project_id 和 `/workspace` mount source 是否匹配。

如果出现 `/workspace 路径不存在` 或容器内 `/workspace` 映射到错误目录，优先检查日志里的 `host_path`、`expected_host_workspace`、`mount_source` 和 `cmd`。

## 开发验证

运行单元测试：

```bash
pytest tests
```

运行 Python 编译检查：

```bash
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall .
```

当前测试覆盖了：

- `/workspace set/status/reset/repair/recreate` 的核心流程。
- 未设置 workspace 时 docker 工具必须返回提示。
- 工作区内宿主机绝对路径到 `/workspace/...` 的改写。
- 不存在路径不会被自动折叠到已存在的父目录。
- 原生工具拦截和 Docker 上下文注入。
