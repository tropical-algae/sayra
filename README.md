# Sayra Backend

Sayra 是一个基于大语言模型的多语言口语练习后端。FastAPI 提供 REST 与
WebSocket 接口，火山引擎负责 ASR/TTS，OpenAI-compatible LLM 负责对话和学习内容。
数据库固定使用 SQLite；文件可由配置选择本地目录或 MinIO。

## 架构边界

```text
src/sayra/
├── app/
│   ├── api/              # FastAPI 路由、依赖、WebSocket
│   ├── schemas/          # HTTP/WebSocket 输入输出模型
│   ├── services/         # 无状态业务函数，只编排 core 能力与少量业务规则
│   ├── container.py      # 应用能力装配与生命周期
│   └── main.py           # FastAPI 入口
├── common/
│   ├── config.py         # 唯一运行配置和 Prompt 文件映射
│   ├── datetime.py       # 时间工具
│   ├── files.py          # 目录、路径与安全文件名工具
│   ├── hashing.py        # 摘要工具
│   └── identifiers.py    # ID 工具
└── core/
    ├── db/
    │   ├── crud/         # session/turn/transcription/audio/conversation 等数据库操作
    │   ├── models.py     # SQLAlchemy 模型
    │   └── session.py    # SQLite Engine、会话与事务生命周期
    ├── storage/          # local/MinIO 实现与工厂
    ├── prompts/
    │   ├── loader.py     # Prompt 加载、校验、渲染算法
    │   └── templates/    # 所有默认 Markdown Prompt
    ├── speech/           # 音频标准化、火山 ASR/TTS
    ├── workflow/         # 对话工作流、事件、Trace、运行时
    ├── llm.py            # OpenAI-compatible LLM 能力
    └── types.py          # Provider 协议及跨能力数据类型
```

依赖方向固定为 `api → app/services → core`。API 不写业务逻辑；service 不写 SQL；
SQL 查询和持久化修改统一位于 `core/db/crud`。每个公开 CRUD 函数完成一个完整的
数据库阶段，并使用 `select_*_by_*`、`insert_*`、`update_*_by_*` 或 `delete_*`
命名。Service 是普通异步函数，不创建只做转发的 class，也不组合一串通用
`get/add/save` 包装函数。

配置中的 `API_PREFIX=/api` 只控制公共挂载路径。版本前缀由
`app/api/routers.py` 在挂载各组接口时统一添加，当前接口位于 `/api/v1`。

## 数据库

配置只需要 SQLite 文件路径：

```dotenv
DATABASE_PATH=./data/sayra.db
DATABASE_ECHO=false
```

`core/db/session.py` 采用模块级 `local_engine` 和 `LocalSession`，负责根据文件路径创建
SQLite Engine、创建父目录并启用外键和 WAL。HTTP 请求通过 FastAPI 的 `get_db`
依赖获得一个 `AsyncSession`，再按 `API → service(db) → CRUD(db)` 显式向下传递；一次
请求内不会重复建立数据库会话。Workflow 等后台任务注入同一个 `LocalSession` 工厂，
并在每个独立数据库阶段创建短生命周期会话。

写操作的提交由对应 CRUD 函数负责。Service 只组合完整 CRUD 与外部能力调用，不管理
SQLAlchemy 查询，也不通过反射装饰器隐式注入数据库连接。

应用启动时调用 `init_db_models()`，通过 `Base.metadata.create_all()` 创建缺失的表和
索引，不需要单独执行数据库初始化命令。`create_all()` 不会修改已有字段类型或删除
旧结构；开发阶段发生不兼容的模型变更时，需要手动处理或重建 SQLite 数据库文件。

## 文件存储

数据库中的 `audio_assets.file_path` 始终保存安全的 POSIX 相对路径，例如：

```text
sessions/{session_id}/turns/{turn_id}/assistant.mp3
```

存储实现按统一规则解析它：

```text
local → STORAGE_ROOT_PATH / file_path
minio → STORAGE_BUCKET / STORAGE_ROOT_PATH / file_path
```

默认本地存储：

```dotenv
STORAGE_TYPE=local
STORAGE_ROOT_PATH=./data/files
STORAGE_BUCKET=sayra
```

MinIO 存储：

```dotenv
STORAGE_TYPE=minio
STORAGE_BUCKET=sayra
STORAGE_ROOT_PATH=audio
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=replace-me
MINIO_SECURE=false
```

业务代码只识别 `file_path`，不会出现 MinIO `object_key` 或本地绝对路径。工厂在启动
时根据 `STORAGE_TYPE` 创建唯一实现；同步 MinIO SDK 和本地文件 I/O 均在线程中运行，
不会阻塞 asyncio 事件循环。

## Prompt 管理

Prompt 正文统一位于 `src/sayra/core/prompts/templates/*.md`，不与 Python 文件混放。
文件映射直接定义在 `src/sayra/common/config.py` 的 `PROMPT_FILES` 中，不再使用额外
TOML。`PROMPT_ROOT` 可切换整套模板目录；应用启动时会一次性检查文件、目录逃逸和
占位符集合，请求期间仅渲染内存模板。

## 本地启动

要求 Python 3.13、uv 和 FFmpeg：

```bash
cp .env.example .env
uv sync
uv run poe run
```

服务默认监听 `http://localhost:8000`，OpenAPI 为 `http://localhost:8000/docs`，健康
检查为 `GET /api/v1/system/health`。

## Docker

默认使用 SQLite 和本地文件卷：

```bash
docker compose up --build
```

需要 MinIO 时，将应用环境中的 `MINIO_ENDPOINT` 设为 `minio:9000`，并启动 profile：

```bash
docker compose --profile minio up --build
```

## 核心配置

| 配置                                            | 用途                                |
| ----------------------------------------------- | ----------------------------------- |
| `DATABASE_PATH`                                 | SQLite 数据库文件                   |
| `STORAGE_TYPE`                                  | `local` 或 `minio`                  |
| `STORAGE_ROOT_PATH`                             | 本地根目录或 MinIO 对象前缀         |
| `STORAGE_BUCKET`                                | MinIO Bucket；local 模式不使用      |
| `MINIO_*`                                       | MinIO 地址和凭证，仅 minio 模式需要 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`    | OpenAI-compatible LLM               |
| `VOLCENGINE_APP_ID` / `VOLCENGINE_ACCESS_TOKEN` | 火山引擎语音凭证                    |
| `DEFAULT_VOICE_ID`                              | 默认 TTS 音色                       |
| `PROMPT_ROOT`                                   | 可选的 Markdown Prompt 目录覆盖     |

完整配置见 `.env.example`。当前任务与事件唤醒器位于进程内，所以 `WORKERS` 必须为
1；SQLite、事件和 Turn 状态仍然持久化，进程重启后会恢复 queued/processing Turn。

## 验证

```bash
uv run poe check
```

测试使用隔离 SQLite 和内存 Provider，不会访问真实 LLM、火山引擎或 MinIO。
