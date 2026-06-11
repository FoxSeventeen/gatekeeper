# Hermes-agent Docker Runtime：Project-centric Workspace Binding 开发方案

> 面向执行者：内网弱模型 / 内网 Agent 开发执行  
> 目标：实现一个以“项目工作区”为核心的 Docker Runtime 插件。用户通过 slash command 设置宿主机项目路径，插件在项目内维护 `.hermes/docker-runtime.json`，并在本机插件状态库 `state.db` 中维护可信绑定。后续任意 session 只要设置到同一个项目路径，都复用该项目对应的 Docker 容器。  
> 核心原则：**Docker 容器绑定主键从 session/root_session_id 改为 project/workspace。Session 只作为当前会话到 project_id 的临时 alias。**

---

## 0. 背景

之前的方案以 session/root_session_id 作为容器绑定主键：

```text
session_id -> root_session_id -> binding_key -> docker_container
```

这个方案能解决长会话中 `session_id` 变化导致容器映射失效的问题，但它不完全符合当前内网开发场景。

当前真实长期对象是：

```text
项目工作区 project1
```

而不是：

```text
某个 Hermes session
```

更符合需求的绑定方式应该是：

```text
project1 -> project_id -> docker_container
```

即：

```text
/path/to/project1/.hermes/docker-runtime.json
  记录 project_id 和 container_name

~/.hermes/plugins/docker_runtime/state.db
  记录本机可信的 project_id -> container_name -> host_workspace

docker labels/mounts
  证明当前容器确实属于该 project，并且挂载了当前 host_workspace
```

---

## 1. 新方案核心结论

采用 **Project-centric Workspace Binding**：

```text
用户通过 slash command 设置工作区：
  /workspace set /absolute/path/to/project1

插件检查项目内 config：
  project1/.hermes/docker-runtime.json

如果 config 不存在：
  初始化 project_id
  创建 container_name
  写项目 config
  创建 Docker 容器
  写 state.db

如果 config 存在：
  读取 project_id/container_name
  查询本机 state.db
  docker inspect 校验 labels 和 mounts
  adopt / recreate / reject

后续所有 session 只要 set 到同一个 project1：
  都通过 project config 找到同一个 project_id
  并复用对应 Docker 容器
```

绑定主链路：

```text
/workspace set <host_workspace>
  -> host_workspace/.hermes/docker-runtime.json
  -> project_id
  -> state.db project_bindings
  -> docker inspect labels/mounts
  -> DockerRuntime
```

当前会话链路：

```text
session_id
  -> session_workspace_aliases
  -> project_id
  -> project_bindings
  -> container_name
```

注意：

```text
session_id/root_session_id 不再是容器绑定主键。
session 只是找到当前 project_id 的 alias。
```

---

## 2. 关键设计目标

### 2.1 项目长期绑定容器

同一个项目目录：

```text
/home/work/project1
```

内部有：

```text
/home/work/project1/.hermes/docker-runtime.json
```

任何用户、任何新 session 后续执行：

```text
/workspace set /home/work/project1
```

都应该复用这个项目对应的 Docker 容器。

### 2.2 项目 config 可见、可迁移

项目内 config 用于让人或工具知道：

```text
这个项目绑定了哪个 Docker runtime
project_id 是什么
container_name 是什么
容器内工作区路径是什么
```

但项目 config 不应作为唯一可信源，因为它在 workspace 内，agent 或用户都可能修改。

### 2.3 state.db 是本机可信索引

插件自己的状态库：

```text
~/.hermes/plugins/docker_runtime/state.db
```

用于记录本机已经确认过的：

```text
project_id -> container_name -> host_workspace
```

它不放在项目目录，不挂载进 Docker，不允许 agent 修改。

### 2.4 Docker labels/mounts 是运行事实校验

即使 state.db 有记录，也不能直接信任。必须用：

```text
docker inspect <container>
```

校验：

```text
labels:
  hermes.plugin=docker-runtime
  hermes.project_id=<project_id>

mounts:
  Source=<当前 host_workspace>
  Destination=/workspace
```

三者一致才可信：

```text
project config
state.db
docker inspect labels/mounts
```

### 2.5 agent 不能设置或修改 workspace

workspace 设置只能由用户 slash command 完成：

```text
/workspace set <absolute_host_path>
```

agent 不应拥有：

```text
set_workspace
find_workspaces
request_workspace
select_workspace
change_workspace
```

这些工具必须不存在或被阻断。

### 2.6 agent 只看到 `/workspace`

宿主机路径只在 slash command 和插件内部使用。

Agent 只应看到：

```text
/workspace
```

容器创建时强制：

```text
-v <host_workspace>:/workspace
-w /workspace
```

### 2.7 terminal 不做路径正则替换

`docker_terminal` 执行命令时：

```bash
docker exec -w /workspace <container> bash -lc "<command>"
```

禁止：

```text
正则匹配 command 中的 host path 并替换
```

只有结构化 path 参数才走 PathMapper：

```text
docker_read_file(path)
docker_write_file(path, content)
docker_patch(path, old, new)
docker_search_files(path, query)
```

---

## 3. 官方接口依据与本地源码查阅位置

> 执行者必须优先查看本地 hermes-agent v0.1.51 源码。如果本地接口和公开文档不一致，以本地源码为准，并记录到 `docs/compat-v0.1.51.md`。

### 3.1 插件注册

优先查看：

```text
website/docs/guides/build-a-hermes-plugin.md
website/docs/user-guide/features/plugins.md
hermes_cli/plugins.py
```

需要确认：

```text
ctx.register_tool
ctx.register_hook
ctx.register_command
```

搜索关键词：

```bash
grep -R "register_tool" -n .
grep -R "register_hook" -n .
grep -R "register_command" -n .
grep -R "PluginContext" -n .
```

### 3.2 Slash command

公开文档中插件可通过：

```python
ctx.register_command(
    name: str,
    handler: Callable[[str], str | None],
    description: str = "",
    args_hint: str = "",
)
```

注册 slash command。

本方案需要注册：

```text
/workspace set <path>
/workspace status
/workspace reset
/workspace recreate
/workspace repair
/workspace fork
/workspace help
```

本地源码查阅：

```text
hermes_cli/plugins.py
hermes_cli/commands.py
website/docs/guides/build-a-hermes-plugin.md
```

搜索：

```bash
grep -R "_plugin_commands" -n .
grep -R "register_command" -n .
grep -R "process_command" -n .
grep -R "slash" -n .
```

如果 v0.1.51 没有 `register_command`，按照本文 fallback 方案处理。

### 3.3 Hooks

需要确认：

```text
pre_llm_call
pre_tool_call
post_tool_call
```

本地源码查阅：

```text
website/docs/user-guide/features/hooks.md
hermes_cli/plugins.py
```

搜索：

```bash
grep -R "pre_llm_call" -n .
grep -R "pre_tool_call" -n .
grep -R "post_tool_call" -n .
grep -R "run_hook" -n .
```

### 3.4 工具运行时与阻断

需要确认工具 dispatch 入口：

```text
tools/registry.py
toolsets.py
website/docs/developer-guide/tools-runtime.md
website/docs/reference/tools-reference.md
```

搜索：

```bash
grep -R "dispatch" -n tools hermes_cli
grep -R "terminal" -n toolsets.py tools
grep -R "execute_code" -n .
grep -R "delegate_task" -n .
grep -R "cronjob" -n .
grep -R "skill_manage" -n .
```

### 3.5 Session storage

虽然容器主键改为 project，但仍建议用 session/root_session_id 维护 session alias。

查阅：

```text
website/docs/developer-guide/session-storage.md
```

搜索：

```bash
grep -R "parent_session_id" -n .
grep -R "state.db" -n .
grep -R "sessions" -n .
```

---

## 4. 推荐目录结构

```text
docker_runtime_plugin/
├── plugin.yaml
├── __init__.py
├── schemas.py
├── config.py
├── errors.py
├── state_store.py
├── session_resolver.py
├── project_config.py
├── workspace_policy.py
├── workspace_commands.py
├── container_manager.py
├── path_mapper.py
├── runtime_resolver.py
├── terminal_ops.py
├── fs_ops.py
├── search_ops.py
├── hooks.py
├── tools.py
├── Dockerfile
├── docs/
│   ├── compat-v0.1.51.md
│   ├── command-spec.md
│   ├── state-db-spec.md
│   ├── project-config-spec.md
│   └── test-report.md
└── tests/
    ├── test_project_config.py
    ├── test_state_store.py
    ├── test_workspace_policy.py
    ├── test_workspace_commands.py
    ├── test_container_manager.py
    ├── test_path_mapper.py
    ├── test_runtime_resolver.py
    ├── test_terminal_ops.py
    ├── test_fs_ops.py
    ├── test_search_ops.py
    └── test_integration_project_binding.py
```

---

## 5. 状态模型

### 5.1 项目 config

路径：

```text
<host_workspace>/.hermes/docker-runtime.json
```

示例：

```json
{
  "schema_version": 1,
  "project_id": "proj_8f3a2c1b9d12",
  "container_name": "hermes-runtime-8f3a2c1b9d12",
  "image": "hermes-docker-runtime:latest",
  "container_workspace": "/workspace",
  "logical_workspace": "/workspace",
  "created_at": "2026-06-10T12:00:00Z",
  "updated_at": "2026-06-10T12:00:00Z",
  "created_by": "hermes-docker-runtime-plugin",
  "binding_mode": "workspace_config",
  "host_workspace_hint": "/home/work/project1"
}
```

说明：

```text
project_id:
  项目长期身份。建议随机生成，不要只用路径 hash。

container_name:
  推荐由 project_id 派生。

host_workspace_hint:
  只是提示，不是可信路径。
  当前 host_workspace 必须来自用户本次 /workspace set 输入。
```

### 5.2 state.db

路径：

```text
~/.hermes/plugins/docker_runtime/state.db
```

表 1：`project_bindings`

```sql
CREATE TABLE IF NOT EXISTS project_bindings (
    project_id TEXT PRIMARY KEY,
    container_name TEXT NOT NULL,
    image TEXT NOT NULL,
    host_workspace TEXT NOT NULL,
    config_path TEXT NOT NULL,
    container_workspace TEXT NOT NULL,
    logical_workspace TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_used_at REAL,
    created_by TEXT NOT NULL
);
```

表 2：`session_workspace_aliases`

```sql
CREATE TABLE IF NOT EXISTS session_workspace_aliases (
    session_id TEXT PRIMARY KEY,
    root_session_id TEXT,
    project_id TEXT NOT NULL,
    seen_at REAL NOT NULL
);
```

表 3：`tool_logs`

```sql
CREATE TABLE IF NOT EXISTS tool_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    session_id TEXT,
    tool_name TEXT NOT NULL,
    args_json TEXT,
    ok INTEGER,
    returncode INTEGER,
    stdout_preview TEXT,
    stderr_preview TEXT,
    duration_ms INTEGER,
    created_at REAL NOT NULL
);
```

### 5.3 Docker labels

创建容器时必须带：

```text
hermes.plugin=docker-runtime
hermes.project_id=<project_id>
hermes.binding_mode=workspace_config
hermes.container_workspace=/workspace
```

可选：

```text
hermes.config_path=<config_path>
hermes.image=<image>
```

---

## 6. 信任模型

必须明确：

```text
用户 slash command 输入的 host path：
  当前操作入口，需要 policy 校验。

项目内 .hermes/docker-runtime.json：
  可迁移 manifest，只能用于发现 project_id/container_name，不能单独信任。

插件 state.db：
  本机可信状态源，但仍需要 Docker inspect 交叉验证。

Docker labels/mounts：
  当前运行事实，证明容器确实属于该 project，并挂载了当前 host_workspace。

agent：
  不可信，不能修改 workspace binding。
```

最终使用容器前必须满足：

```text
project config、state.db、docker inspect 三者一致。
```

或者进入明确的 import/adopt/recreate 流程。

---

## 7. 核心流程

### 7.1 第一次初始化项目

用户：

```text
/workspace set /home/work/project1
```

如果：

```text
/home/work/project1/.hermes/docker-runtime.json 不存在
```

流程：

```text
1. 校验 host_workspace
2. 创建 .hermes 目录
3. 生成 project_id
4. 生成 container_name
5. 写 project config
6. 创建 Docker 容器
7. 写 state.db project_bindings
8. 写 session_workspace_aliases
9. 返回成功
```

结果：

```text
project1/.hermes/docker-runtime.json 存在
state.db 有 project_id 记录
Docker 容器 running
当前 session 绑定到 project_id
```

### 7.2 已有本机记录的项目

用户：

```text
/workspace set /home/work/project1
```

如果 config 存在，state.db 也有该 project_id：

```text
1. 校验 host_workspace
2. 读取 project config
3. 查询 state.db project_bindings
4. 比较 config 和 state.db
5. docker inspect 校验 labels/mounts
6. 通过后复用容器
7. 更新 session alias
8. 更新 last_used_at
```

### 7.3 从其他地方复制来的项目

用户：

```text
/workspace set /data/imported/project1
```

如果 config 存在，但 state.db 没有该 project_id：

```text
进入 foreign config import/adopt 流程
```

#### 情况 A：config 指向的容器不存在

```text
docker inspect <container_name> 失败
```

处理：

```text
1. 保留原 project_id
2. 使用原 container_name，若无冲突则创建容器
3. 挂载当前 host_workspace 到 /workspace
4. 写入 state.db
5. 更新 config 的 updated_at/host_workspace_hint
6. 写 session alias
```

返回：

```text
检测到已有项目 config，但当前机器没有对应容器。
已在当前机器重新创建容器并导入 state.db。
```

#### 情况 B：容器存在且 label/mount 匹配

处理：

```text
1. adopt 现有容器
2. 写入 state.db
3. 写 session alias
```

返回：

```text
检测到本机容器和项目 config 匹配。
已导入当前插件 state.db。
```

#### 情况 C：容器存在但 label 不匹配

处理：

```text
拒绝绑定。
提示用户执行 /workspace recreate。
```

返回：

```text
检测到容器名冲突或 label 不匹配。
为避免误用错误容器，本次绑定已拒绝。
请执行 /workspace recreate。
```

#### 情况 D：容器 label 匹配但 mount source 不匹配

处理：

```text
拒绝绑定。
提示用户执行 /workspace recreate。
```

返回：

```text
检测到 project_id 一致，但容器挂载路径和当前 workspace 不一致。
请执行 /workspace recreate 以当前路径重建容器。
```

### 7.4 recreate

命令：

```text
/workspace recreate
```

作用：

```text
以当前 host_workspace 和 project_id 重新创建本机 Docker 容器。
```

流程：

```text
1. 当前 session 必须已有 pending 或 loaded project config
2. 读取 project_id
3. 如果旧容器存在且由本插件创建：
   - stop
   - rm，或保留并换新名字，取决于配置
4. 生成或复用 container_name
5. 创建新容器
6. 更新 config
7. 更新 state.db
8. 更新 session alias
```

MVP 推荐：

```text
recreate 使用同一个 project_id
container_name 默认仍使用 hermes-runtime-<project_id_short>
如果同名容器冲突且 label 不匹配，则生成新 container_name 并更新 config
```

### 7.5 fork

命令：

```text
/workspace fork
```

用途：

```text
项目是复制出来的新副本，希望拥有独立 project_id 和独立 Docker 容器。
```

流程：

```text
1. 当前 workspace 必须已 set
2. 生成新的 project_id
3. 生成新的 container_name
4. 覆盖当前项目 config
5. 创建新容器
6. 写 state.db
7. 当前 session alias 指向新 project_id
```

MVP 可以先不实现，但要在设计中预留。

### 7.6 reset

命令：

```text
/workspace reset
```

建议语义：

```text
只解除当前 session 与 project_id 的关联。
不删除项目 config。
不删除 Docker 容器。
不删除 project_bindings。
```

如果需要销毁项目级绑定，另设：

```text
/workspace destroy
```

MVP 可以不做 destroy。

---

## 8. Slash command 设计

注册命令：

```python
ctx.register_command(
    "workspace",
    handler=handle_workspace_command,
    description="Manage project-centric Docker workspace binding",
    args_hint="set <path> | status | reset | recreate | repair | fork | help",
)
```

命令列表：

```text
/workspace help
/workspace set <absolute_host_path>
/workspace status
/workspace reset
/workspace recreate
/workspace repair
/workspace fork
```

### 8.1 `/workspace help`

输出：

```text
Usage:
  /workspace set <absolute_host_path>
  /workspace status
  /workspace reset
  /workspace recreate
  /workspace repair
  /workspace fork

说明:
  workspace 必须由用户直接通过 slash command 设置。
  agent 不能设置或修改 workspace。
  设置后，host 项目目录会挂载到 Docker 容器 /workspace。
```

### 8.2 `/workspace set <path>`

负责初始化、导入、复用项目绑定。

TODO：

- [ ] 解析 path，支持空格路径，使用 `shlex.split`
- [ ] path 必须是绝对路径
- [ ] 调用 workspace_policy 校验
- [ ] 调用 project_config 读取或初始化 config
- [ ] 查询 state.db
- [ ] 按新项目/已有项目/foreign config 分流
- [ ] 创建或复用 Docker 容器
- [ ] 写 session alias
- [ ] 返回清晰状态

### 8.3 `/workspace status`

显示：

```text
Session status:
  session_id
  root_session_id
  project_id

Project config:
  config_path
  container_name

State DB:
  host_workspace
  state
  last_used_at

Docker:
  container_name
  running
  mount source
  mount destination
```

TODO：

- [ ] 未绑定时显示 UNBOUND
- [ ] 已绑定时显示 LOCKED
- [ ] state/config/docker 不一致时显示 BROKEN
- [ ] 不把过多敏感 host 信息注入给 LLM，slash command 输出给用户可以显示

### 8.4 `/workspace reset`

TODO：

- [ ] 删除当前 session alias
- [ ] 不删除 project config
- [ ] 不删除 project_bindings
- [ ] 不删除容器
- [ ] 返回当前 session 已解绑

### 8.5 `/workspace recreate`

TODO：

- [ ] 当前 session 必须已有 project config 或 pending import context
- [ ] 校验 host_workspace
- [ ] 使用已有 project_id
- [ ] 处理同名容器冲突
- [ ] 重新创建容器
- [ ] 更新 state.db
- [ ] 更新 project config
- [ ] 写 session alias

### 8.6 `/workspace repair`

语义：

```text
尝试自动修复 BROKEN 状态。
```

repair 可以覆盖：

```text
container stopped -> start
container missing -> create
state.db missing but container valid -> adopt
```

repair 不应覆盖：

```text
label 不匹配
mount source 不匹配
container name 被其他项目占用
```

这些需要 recreate。

### 8.7 `/workspace fork`

TODO：

- [ ] 可作为 P1/P2 功能
- [ ] 生成新 project_id
- [ ] 生成新 container_name
- [ ] 覆盖当前项目 config
- [ ] 新建容器
- [ ] 写 state.db
- [ ] 当前 session alias 指向新 project_id

---

## 9. 模块职责与 TODO

### 9.1 `project_config.py`

职责：读写项目内 config。

需要实现：

```python
@dataclass
class ProjectConfig:
    schema_version: int
    project_id: str
    container_name: str
    image: str
    container_workspace: str
    logical_workspace: str
    created_at: str
    updated_at: str
    created_by: str
    binding_mode: str
    host_workspace_hint: str | None
```

函数：

```python
config_path_for_workspace(host_workspace: Path) -> Path
read_project_config(host_workspace: Path) -> ProjectConfig | None
create_project_config(host_workspace: Path, image: str) -> ProjectConfig
write_project_config(host_workspace: Path, config: ProjectConfig) -> None
validate_project_config(config: ProjectConfig) -> None
generate_project_id() -> str
container_name_for_project(project_id: str) -> str
```

TODO：

- [ ] 实现 config 路径 `.hermes/docker-runtime.json`
- [ ] config 不存在返回 None
- [ ] config 存在时解析 JSON
- [ ] 校验 schema_version
- [ ] 校验 project_id 格式
- [ ] 校验 container_name 格式
- [ ] 校验 container_workspace 必须是 `/workspace`
- [ ] 校验 logical_workspace 必须是 `/workspace`
- [ ] 创建 config 时自动 mkdir `.hermes`
- [ ] 写 config 使用 atomic write
- [ ] 可选：增加 HMAC 签名字段
- [ ] 写单元测试

禁止：

- [ ] 不要让 agent tool 直接写 config
- [ ] 不要把 config 当作唯一可信源

### 9.2 `state_store.py`

职责：维护本机可信状态。

需要实现：

```python
get_project_binding(project_id)
upsert_project_binding(binding)
mark_project_state(project_id, state)
delete_session_alias(session_id)
get_project_id_for_session(session_id)
upsert_session_alias(session_id, root_session_id, project_id)
insert_tool_log(...)
update_last_used_at(project_id)
```

TODO：

- [ ] 创建 state.db
- [ ] 创建 project_bindings
- [ ] 创建 session_workspace_aliases
- [ ] 创建 tool_logs
- [ ] 写事务
- [ ] SQLite timeout
- [ ] 并发写保护
- [ ] 插件重启后能恢复

### 9.3 `workspace_policy.py`

职责：校验用户 slash command 输入的 host path。

规则：

```text
必须是绝对路径
必须存在
必须是目录
必须在 allowed_roots 内，若配置了 allowed_roots
不能是 deny_roots
resolve 后不能 symlink 逃逸
```

deny_roots 默认：

```text
/
/etc
/root
/home
/usr
/var
/bin
/sbin
```

TODO：

- [ ] 实现绝对路径校验
- [ ] 实现存在性校验
- [ ] 实现目录校验
- [ ] 实现 allowed_roots
- [ ] 实现 deny_roots
- [ ] 实现 symlink resolve
- [ ] 实现项目 marker 检测，可选
- [ ] 写单元测试

### 9.4 `container_manager.py`

职责：Docker 容器生命周期和校验。

函数：

```python
create_container(project_config, host_workspace)
inspect_container(container_name)
container_exists(container_name)
container_running(container_name)
start_container(container_name)
stop_container(container_name)
remove_container(container_name)
validate_container_for_project(container_info, project_config, host_workspace)
ensure_container_for_binding(binding)
```

容器创建：

```bash
docker run -d \
  --name <container_name> \
  --label hermes.plugin=docker-runtime \
  --label hermes.project_id=<project_id> \
  --label hermes.binding_mode=workspace_config \
  --label hermes.container_workspace=/workspace \
  -v <host_workspace>:/workspace \
  -w /workspace \
  --network none \
  <image> \
  sleep infinity
```

TODO：

- [ ] 所有 Docker 命令使用参数数组
- [ ] 不用 `shell=True`
- [ ] 创建时加 labels
- [ ] 校验 labels
- [ ] 校验 mount source
- [ ] 校验 mount destination
- [ ] stopped 容器自动 start
- [ ] label 不匹配拒绝
- [ ] mount 不匹配拒绝
- [ ] 容器不存在时按流程 create/recreate
- [ ] 写集成测试

### 9.5 `workspace_commands.py`

职责：实现 `/workspace ...`。

核心函数：

```python
handle_workspace_command(raw_args: str, **context) -> str
workspace_set(path: str, context) -> str
workspace_status(context) -> str
workspace_reset(context) -> str
workspace_recreate(context) -> str
workspace_repair(context) -> str
workspace_fork(context) -> str
```

TODO：

- [ ] 解析 raw_args
- [ ] 支持 help/status/set/reset/recreate/repair/fork
- [ ] set 实现新项目初始化
- [ ] set 实现已有项目复用
- [ ] set 实现 foreign config import/adopt
- [ ] recreate 实现冲突处理
- [ ] reset 只删除 session alias
- [ ] status 显示 config/state/docker 三方状态
- [ ] 错误信息清晰
- [ ] 写单元测试

### 9.6 `runtime_resolver.py`

职责：从当前 session 找到 project runtime。

流程：

```text
1. 获取 session_id
2. 查 session_workspace_aliases 得到 project_id
3. 查 project_bindings
4. docker inspect 校验 labels/mounts
5. ensure container running
6. 构造 PathMapper
7. 返回 DockerRuntime
```

未绑定时返回：

```text
WorkspaceNotSet:
  请用户输入 /workspace set <absolute_host_path>
```

TODO：

- [ ] 实现 resolve_runtime
- [ ] 未绑定报错
- [ ] binding 缺失报错或提示 repair
- [ ] docker 校验失败报错
- [ ] 自动 start stopped container
- [ ] 写测试

### 9.7 `path_mapper.py`

职责：只处理结构化 path 参数。

允许：

```text
src/a.py
./src/a.py
/workspace/src/a.py
<host_workspace>/src/a.py
```

输出：

```text
/workspace/src/a.py
```

拒绝：

```text
/etc/passwd
/root/.ssh/id_rsa
../../outside.txt
/other/project/file.py
```

特殊保护：

```text
禁止 docker_write_file/docker_patch 修改：
  /workspace/.hermes/docker-runtime.json
```

可选禁止整个目录写：

```text
/workspace/.hermes/
```

TODO：

- [ ] 实现 to_container
- [ ] 实现 to_logical
- [ ] 实现 workspace 外路径拒绝
- [ ] 实现路径穿越拒绝
- [ ] 实现 protected path 检查
- [ ] 明确禁止 command rewrite
- [ ] 写测试

### 9.8 `terminal_ops.py`

职责：容器内执行命令。

执行：

```bash
docker exec -w /workspace <container> bash -lc "<command>"
```

禁止：

```text
不解析 command
不正则替换 command 路径
不猜测 host path
```

TODO：

- [ ] 实现 docker_terminal
- [ ] 支持 timeout
- [ ] 捕获 stdout/stderr/returncode
- [ ] 返回 duration_ms
- [ ] 写 tool log
- [ ] 如果未绑定 workspace，返回提示
- [ ] 如果命令使用 host path 失败，只提示使用 /workspace 或相对路径，不自动修复

### 9.9 `fs_ops.py`

职责：容器内文件读写修改。

工具：

```text
docker_read_file
docker_write_file
docker_patch
docker_list_files
```

TODO：

- [ ] 所有 path 走 PathMapper
- [ ] read_file 可读 `.hermes/docker-runtime.json`
- [ ] write_file 禁止写 `.hermes/docker-runtime.json`
- [ ] patch 禁止改 `.hermes/docker-runtime.json`
- [ ] 使用 Python 脚本在容器内读写
- [ ] content 通过 stdin 传递
- [ ] 不把 content 拼进 shell
- [ ] 返回 `/workspace/...` 路径
- [ ] 写测试

### 9.10 `search_ops.py`

职责：容器内搜索。

TODO：

- [ ] path 走 PathMapper
- [ ] query 不能为空
- [ ] 优先 rg
- [ ] fallback Python
- [ ] 只搜索 `/workspace`
- [ ] 返回 `/workspace/...`
- [ ] 写测试

### 9.11 `hooks.py`

职责：注入规则和阻断 host 工具。

#### pre_llm_call

如果未绑定 workspace：

```text
[docker-runtime]
当前会话尚未设置 workspace。
请提示用户输入：
  /workspace set <absolute_host_path>
在 workspace 设置前，不要尝试执行 terminal 或文件操作。
```

如果已绑定：

```text
[docker-runtime]
当前会话使用 Docker Workspace Runtime。
项目根目录是 /workspace。
所有 shell 命令必须使用 docker_terminal。
文件读取、写入、修改、搜索必须使用 docker_read_file/docker_write_file/docker_patch/docker_search_files。
不要使用 host 绝对路径。
workspace 只能由用户 slash command /workspace set 设置，agent 不能修改。
```

#### pre_tool_call

MVP 推荐 allowlist：

```python
ALLOWED_TOOLS = {
    "docker_terminal",
    "docker_read_file",
    "docker_write_file",
    "docker_patch",
    "docker_search_files",
    "docker_list_files",
    "docker_runtime_status",
    "clarify",
    "todo",
}
```

必须阻断：

```python
BLOCKED_TOOLS = {
    "terminal",
    "process",
    "read_file",
    "write_file",
    "patch",
    "search_files",
    "list_files",
    "execute_code",
    "delegate_task",
    "cronjob",
    "skill_manage",
    "set_workspace",
    "request_workspace",
    "find_workspaces",
    "change_workspace",
    "select_workspace",
}
```

MCP/未知插件工具：

```text
MVP 默认阻断，除非内网明确不存在这些工具。
```

TODO：

- [ ] 实现 pre_llm_call
- [ ] 实现 pre_tool_call
- [ ] docker_* 允许
- [ ] host file/shell/code/subagent 工具阻断
- [ ] 未知工具默认 deny 或内网配置 allowlist
- [ ] 写测试

### 9.12 `tools.py`

Agent 可见工具：

```text
docker_terminal
docker_read_file
docker_write_file
docker_patch
docker_search_files
docker_list_files
docker_runtime_status
```

Agent 不可见工具：

```text
set_workspace
request_workspace
find_workspaces
```

TODO：

- [ ] 定义 schemas
- [ ] 实现 handlers
- [ ] handler 接收 `args: dict, **kwargs`
- [ ] handler 返回 JSON string
- [ ] handler 捕获异常
- [ ] handler 写 tool log
- [ ] 未绑定 workspace 时返回 WorkspaceNotSet

---

## 10. 插件注册

`__init__.py`：

```python
def register(ctx):
    # tools
    ctx.register_tool(...)
    ctx.register_tool(...)
    ctx.register_tool(...)

    # hooks
    ctx.register_hook("pre_llm_call", inject_docker_context)
    ctx.register_hook("pre_tool_call", block_native_tools)

    # slash command
    ctx.register_command(
        "workspace",
        handler=handle_workspace_command,
        description="Manage project-centric Docker workspace binding",
        args_hint="set <path> | status | reset | recreate | repair | fork | help",
    )
```

TODO：

- [ ] 注册所有 docker_* tools
- [ ] 注册 hooks
- [ ] 注册 `/workspace`
- [ ] 确认 command handler 能拿到 session context
- [ ] 如果 handler 只有 raw_args，则用闭包或上下文 API 获取 session_id
- [ ] 如果 register_command 不存在，进入 fallback

---

## 11. Slash command fallback

优先级：

```text
1. ctx.register_command
2. CLI command dispatch patch
3. gateway command dispatch patch
4. pre-LLM 用户消息拦截，前提是能中断 LLM
```

必须先调研 v0.1.51。

TODO：

- [ ] 确认 register_command 是否存在
- [ ] 确认 command handler 是否能访问 session_id
- [ ] 确认 CLI/gateway 是否都生效
- [ ] 无法注册时 patch command dispatch
- [ ] 记录到 compat-v0.1.51.md

---

## 12. Docker 镜像

Dockerfile：

```Dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    bash \
    git \
    python3 \
    python3-pip \
    ripgrep \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["sleep", "infinity"]
```

TODO：

- [ ] 新建 Dockerfile
- [ ] 构建 `hermes-docker-runtime:latest`
- [ ] 确认 bash/python3/rg 可用
- [ ] 确认 `/workspace` 可写
- [ ] 支持 `--user uid:gid` 可选
- [ ] 默认 `--network none`

---

## 13. 测试计划

### 13.1 新项目初始化

```text
/workspace set /tmp/project1
```

预期：

```text
project1/.hermes/docker-runtime.json 创建
state.db project_bindings 有记录
Docker 容器创建
容器挂载 /tmp/project1:/workspace
session alias 写入
```

### 13.2 同项目新 session 复用

```text
新 session 执行：
/workspace set /tmp/project1
```

预期：

```text
读取 project config
查询 state.db
docker inspect 通过
复用同一容器
```

### 13.3 state.db 丢失但容器存在且匹配

操作：

```text
删除 state.db
保留 Docker 容器
/workspace set /tmp/project1
```

预期：

```text
config 存在
state.db 无记录
docker inspect label/mount 匹配
adopt 到 state.db
```

### 13.4 项目复制到新机器/新目录，容器不存在

操作：

```text
复制 project1 到 /tmp/imported_project1
当前 Docker 没有 config 中的容器
/workspace set /tmp/imported_project1
```

预期：

```text
保留 project_id
重新创建容器
写 state.db
更新 config host_workspace_hint
```

### 13.5 容器名冲突 label 不匹配

操作：

```text
创建同名容器但 label 不匹配
/workspace set project1
```

预期：

```text
拒绝绑定
提示 /workspace recreate
```

### 13.6 mount source 不匹配

操作：

```text
容器 label project_id 匹配
但 mount source 是旧路径
/workspace set 新路径
```

预期：

```text
拒绝绑定
提示 /workspace recreate
```

### 13.7 recreate

```text
/workspace recreate
```

预期：

```text
重建容器
挂载当前路径
更新 state.db/config
```

### 13.8 fork

```text
/workspace fork
```

预期：

```text
生成新 project_id
生成新 container
覆盖当前项目 config
写 state.db
```

P1/P2 可实现。

### 13.9 工具一致性

```text
docker_terminal("echo hello > a.txt")
docker_read_file("a.txt")
docker_write_file("a.txt", "world")
docker_terminal("cat a.txt")
docker_patch("a.txt", "world", "hermes")
docker_read_file("a.txt")
```

预期：

```text
全部操作同一个 /workspace/a.txt
```

### 13.10 protected config

```text
docker_write_file("/workspace/.hermes/docker-runtime.json", "bad")
docker_patch("/workspace/.hermes/docker-runtime.json", ...)
```

预期：

```text
拒绝修改
```

注意：terminal 理论上仍可修改 config，所以使用容器前仍必须三方校验。

### 13.11 原生工具阻断

测试：

```text
terminal
process
read_file
write_file
patch
search_files
execute_code
delegate_task
cronjob
skill_manage
set_workspace
```

预期：

```text
全部 block
```

---

## 14. 开发阶段计划

### Phase 0：兼容调研

TODO：

- [ ] 确认 v0.1.51 插件接口
- [ ] 确认 register_command
- [ ] 确认 command handler 能否拿 session_id
- [ ] 确认 hook 阻断格式
- [ ] 确认内网工具清单
- [ ] 确认 Docker 可用性
- [ ] 输出 `docs/compat-v0.1.51.md`

### Phase 1：project config 与 state.db

TODO：

- [ ] 实现 errors.py
- [ ] 实现 config.py
- [ ] 实现 project_config.py
- [ ] 实现 state_store.py
- [ ] 写单元测试

验收：

- [ ] 能创建 `.hermes/docker-runtime.json`
- [ ] 能读取已有 config
- [ ] 能初始化 state.db
- [ ] 能写 project_bindings/session_aliases/tool_logs

### Phase 2：workspace policy 和 command

TODO：

- [ ] 实现 workspace_policy.py
- [ ] 实现 workspace_commands.py
- [ ] 实现 `/workspace help/status/set/reset`
- [ ] 接入 slash command
- [ ] 写测试

验收：

- [ ] 用户能 set workspace
- [ ] 非法路径被拒绝
- [ ] reset 只解绑当前 session
- [ ] status 能显示状态

### Phase 3：container manager 与三方校验

TODO：

- [ ] 实现 container_manager.py
- [ ] 实现 Docker labels
- [ ] 实现 mount 校验
- [ ] 实现 create/adopt/recreate
- [ ] 写集成测试

验收：

- [ ] 新项目创建容器
- [ ] state.db 缺失时 adopt
- [ ] foreign config 容器不存在时重建
- [ ] label/mount 不匹配时拒绝

### Phase 4：Docker-aware 工具

TODO：

- [ ] 实现 path_mapper.py
- [ ] 实现 runtime_resolver.py
- [ ] 实现 terminal_ops.py
- [ ] 实现 fs_ops.py
- [ ] 实现 search_ops.py
- [ ] 实现 tools.py
- [ ] 写测试

验收：

- [ ] terminal/read/write/patch/search 全部操作同一 `/workspace`
- [ ] protected config 禁止通过 file tools 修改
- [ ] terminal 不做命令路径替换

### Phase 5：hooks 和阻断

TODO：

- [ ] 实现 pre_llm_call
- [ ] 实现 pre_tool_call
- [ ] 配置 allowlist/denylist
- [ ] 阻断原生 host 工具
- [ ] 阻断 workspace 修改工具
- [ ] 写测试

验收：

- [ ] agent 知道 `/workspace`
- [ ] agent 不能 set workspace
- [ ] agent 不能调用原生 host 工具

### Phase 6：迁移与异常场景

TODO：

- [ ] 实现 `/workspace recreate`
- [ ] 实现 `/workspace repair`
- [ ] 预留 `/workspace fork`
- [ ] 测试项目复制场景
- [ ] 测试 state.db 删除场景
- [ ] 测试容器冲突场景
- [ ] 输出 test-report

---

## 15. 禁止事项

开发过程中禁止：

- [ ] 不要用 session_id 作为容器绑定主键
- [ ] 不要只信项目 config
- [ ] 不要只信 state.db
- [ ] 不要只信 container_name
- [ ] 不要跳过 Docker label/mount 校验
- [ ] 不要让 agent 设置 workspace
- [ ] 不要注册 set_workspace/find_workspaces/request_workspace agent tool
- [ ] 不要只拦截 terminal
- [ ] 不要让原生 read_file/patch 继续走 host
- [ ] 不要正则替换 terminal command 中的路径
- [ ] 不要默认开放 Docker network
- [ ] 不要误用非本插件创建的容器
- [ ] 不要让 file tools 修改 `.hermes/docker-runtime.json`
- [ ] 不要自动复用 label/mount 不匹配的容器

---

## 16. 最小成功 Demo

### Step 1：用户初始化项目

```text
/workspace set /home/work/demo_project
```

期望：

```text
创建 /home/work/demo_project/.hermes/docker-runtime.json
创建 Docker 容器
写 state.db
返回 container_workspace=/workspace
```

### Step 2：agent 写文件

```text
docker_write_file("/workspace/hello.py", "print(\"hello\")\n")
```

### Step 3：agent 执行

```text
docker_terminal("python3 hello.py")
```

期望：

```text
hello
```

### Step 4：新 session 复用

新会话：

```text
/workspace set /home/work/demo_project
```

期望：

```text
读取项目 config
复用同一 Docker 容器
```

### Step 5：state.db 删除后恢复

删除本机 state.db 后：

```text
/workspace set /home/work/demo_project
```

如果容器还在且 label/mount 匹配：

```text
adopt 到 state.db
```

### Step 6：复制项目到新目录

```text
cp -r /home/work/demo_project /home/work/demo_project_copy
/workspace set /home/work/demo_project_copy
```

如果容器 mount 不匹配：

```text
提示 /workspace recreate
```

如果当前机器没有 config 中容器：

```text
使用原 project_id 在当前机器创建容器
```

如用户希望副本独立：

```text
/workspace fork
```

---

## 17. 最终验收标准

- [ ] `/workspace set <path>` 可初始化新项目
- [ ] 项目内生成 `.hermes/docker-runtime.json`
- [ ] 同一项目新 session 可复用同一容器
- [ ] 容器绑定主键是 project_id，不是 session_id
- [ ] state.db 存本机可信 project binding
- [ ] Docker labels/mounts 每次使用前校验
- [ ] state.db 缺失但容器匹配时可 adopt
- [ ] config 复制过来但容器不存在时可本机重建
- [ ] label 不匹配时拒绝
- [ ] mount source 不匹配时拒绝并提示 recreate
- [ ] agent 只看到 `/workspace`
- [ ] terminal 不做路径正则替换
- [ ] file tools 禁止修改 `.hermes/docker-runtime.json`
- [ ] 原生 host 工具被阻断
- [ ] slash command 是唯一 workspace 设定入口
- [ ] 有完整单元测试和集成测试

---

## 18. 给内网 Agent 的严格执行顺序

```text
1. 调研 v0.1.51 插件接口和 command 接口
2. 写 docs/compat-v0.1.51.md
3. 实现 config.py
4. 实现 errors.py
5. 实现 project_config.py
6. 实现 state_store.py
7. 实现 workspace_policy.py
8. 实现 session_resolver.py
9. 实现 workspace_commands.py
10. 注册 /workspace slash command
11. 实现 container_manager.py
12. 写 Dockerfile
13. 实现 path_mapper.py
14. 实现 runtime_resolver.py
15. 实现 terminal_ops.py
16. 实现 fs_ops.py
17. 实现 search_ops.py
18. 实现 tools.py
19. 实现 hooks.py
20. 实现 __init__.py
21. 写单元测试
22. 写 Docker 集成测试
23. 跑最小成功 Demo
24. 测试 state.db 缺失 adopt
25. 测试 foreign config recreate
26. 测试 label/mount 不匹配拒绝
27. 输出 docs/test-report.md
```

---

## 19. 一句话总结

最终方案是：

```text
项目目录内 config 负责可迁移发现；
插件 state.db 负责本机可信索引；
Docker labels/mounts 负责运行事实校验；
session 只记录当前会话使用哪个 project_id；
真正的容器绑定主键是 project_id。
```

因此：

```text
/workspace set /path/to/project1
  -> project1/.hermes/docker-runtime.json
  -> project_id
  -> state.db
  -> docker inspect
  -> docker container
```

这套方案支持：

```text
新 session 复用容器
项目复制后的 import/adopt/recreate
项目长期记录自己的 Docker runtime
agent 只在 /workspace 中工作
```
