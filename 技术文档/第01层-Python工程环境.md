# xinghao-db-analyze 第 01 层

## Python 工程环境、环境变量、日志与系统常量

## 1. 本层目标

完成后，复刻项目应当具备：

- Python 3.11 虚拟环境；
- 完整 Python 依赖声明；
- `dev`、`test`、`pro` 三种配置环境；
- 本地和容器环境日志目录识别；
- 控制台彩色日志；
- 每日轮转的文件日志；
- 日志配置失败时的降级机制；
- 四种问答意图、SSE 数据类型和系统状态码；
- Dify API 地址构造能力。

本层不启动 Sanic，不连接 PostgreSQL、MinIO 或 LLM。

## 2. 本层文件

```text
xinghao-db-analyze/
├── .env.dev
├── .env.pro
├── .env.test
├── .gitignore
├── README.md
├── REPLICATION-COVERAGE.md
├── pyproject.toml
├── config/
│   ├── __init__.py
│   ├── load_env.py
│   └── logging.conf
└── constants/
    ├── __init__.py
    ├── code_enum.py
    └── dify_rest_api.py
```

## 3. 创建完整 Python 环境

进入复刻项目：

```powershell
cd D:\PycharmProjects\PersonUser\xinghao-db-analyze
```

按照原项目完整手敲 `pyproject.toml`。依赖列表、阿里云 uv 源和 Black 配置都要保留。不要手敲 `uv.lock`，它由 uv 生成。

创建和激活环境：

```powershell
uv venv --python 3.11
.\.venv\Scripts\Activate.ps1
uv sync
```

基础验证：

```powershell
python --version
uv tree
python -c "import sanic, sqlalchemy, langchain, langgraph, duckdb; print('依赖环境正常')"
```

预期：

```text
Python 3.11.x
依赖环境正常
```

## 4. 创建环境文件

`.env.test` 和 `.env.pro` 暂时保持空文件。

`.env.dev`：

```dotenv
SERVER_PORT=8088
SERVER_WORKERS=1

MINIO_ENDPOINT=127.0.0.1:9000

SQLALCHEMY_DATABASE_URI=postgresql+psycopg2://aix_db:1@127.0.0.1:15432/aix_db

LANGFUSE_TRACING_ENABLED=false
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_BASE_URL=http://localhost:3000

VITE_ENABLE_PAGE_AGENT=false
```

不要复制原项目中的真实密钥。

单独验证环境文件：

```powershell
python -c "from dotenv import load_dotenv; import os; load_dotenv('.env.dev'); print(os.getenv('SERVER_PORT')); print(os.getenv('SERVER_WORKERS'))"
```

预期：

```text
8088
1
```

## 5. 创建日志配置

创建 `config` 包：

```powershell
New-Item -ItemType Directory -Force config
New-Item -ItemType File -Force config\__init__.py
```

按照原项目手敲 `config/logging.conf`。

日志结构：

```text
root logger
├── consoleHandler
│   └── coloredFormatter
└── fileHandler
    └── fileFormatter
```

文件 Handler 的关键配置：

```ini
args=('logs/assistant.log', 'midnight', 1, 5, 'utf8')
```

它表示每天午夜轮转并保留最近五份日志。

不需要手动建立 `logs` 目录。`load_env()` 会在运行时建立：

```text
logs/
└── assistant.log
```

## 6. 创建环境和日志加载器

按照原项目完整手敲 `config/load_env.py`。必须保留以下功能分支：

1. `/xinghao-db-analyze` 存在时使用容器日志目录；
2. 本地运行时使用 `logs`；
3. 自动创建目录和日志文件；
4. 检查 `colorlog`；
5. 找不到 `colorlog` 时替换彩色 Formatter；
6. 使用临时配置文件完成日志降级；
7. 清除 Root Logger 已有 Handler；
8. 统一项目 Logger 的级别和传播；
9. `logging.conf` 失败时使用 `basicConfig`；
10. 根据 `ENV` 选择 `.env.dev`、`.env.test` 或 `.env.pro`。

默认配置选择逻辑：

```python
dotenv_path = f'.env.{os.getenv("ENV", "dev")}'
load_dotenv(dotenv_path)
```

从项目根目录验证：

```powershell
python -c "from config.load_env import load_env; load_env(); import os, logging; logging.info('环境加载成功'); print(os.getenv('SERVER_PORT'))"
```

预期控制台出现：

```text
Logging configuration loaded successfully...
====当前配置文件是 .env.dev====
环境加载成功
8088
```

并检查：

```powershell
Get-ChildItem logs
Get-Content logs\assistant.log
```

## 7. 验证环境切换

验证生产环境：

```powershell
$env:ENV="pro"
python -c "from config.load_env import load_env; load_env()"
Remove-Item Env:ENV
```

输出应当包含：

```text
.env.pro
```

验证日志降级分支时，可以临时将 `config/logging.conf` 改名，执行测试后再恢复。不要在有未提交改动时进行该操作。

## 8. 创建系统常量

创建：

```powershell
New-Item -ItemType Directory -Force constants
New-Item -ItemType File -Force constants\__init__.py
```

按照原项目完整手敲：

```text
constants/code_enum.py
constants/dify_rest_api.py
```

`code_enum.py` 必须覆盖：

- `SysCodeEnum`
- `IntentEnum`
- `get_qatype_name()`
- `DataTypeEnum`
- `DiFyCodeEnum`

源码中的以下值暂时保持原样：

```python
c_400 = (401, "无效Token", "无效Token")
```

不要在复刻阶段自行将 `401` 修改为 `400`。

验证：

```powershell
python -c "from constants.code_enum import IntentEnum, DataTypeEnum, get_qatype_name; print(IntentEnum.DATABASE_QA.value); print(DataTypeEnum.ANSWER.value); print(get_qatype_name('REPORT_QA'))"
```

预期：

```text
('DATABASE_QA', '数据问答')
('t02', '答案')
深度搜索
```

## 9. 验证 Dify URL

```powershell
$env:DIFY_SERVER_URL="http://localhost:5001"

python -c "from constants.dify_rest_api import DiFyRestApi; print(DiFyRestApi.build_url(DiFyRestApi.DIFY_REST_CHAT)); print(DiFyRestApi.replace_path_params(DiFyRestApi.DIFY_REST_STOP, {'task_id': 123}))"

Remove-Item Env:DIFY_SERVER_URL
```

预期：

```text
http://localhost:5001/v1/chat-messages
http://localhost:5001/v1/chat-messages/123/stop
```

## 10. 全层验证

```powershell
python -m compileall config constants
python -c "from config.load_env import load_env; load_env(); import os; print(os.getenv('SERVER_PORT'))"
git status
```

本层完成标准：

- `uv sync` 成功；
- Python 为 3.11；
- 核心依赖可以导入；
- `.env.dev` 正常加载；
- `logs/assistant.log` 自动生成；
- 控制台和文件日志正常；
- `dev`、`pro` 环境可以切换；
- 所有常量可以导入；
- Dify URL 构造结果正确；
- `compileall` 无错误。

## 11. 更新覆盖表

```markdown
| `pyproject.toml` | Python 工程环境 | `pyproject.toml` | VERIFIED | `uv sync` 通过 |
| `.env.dev` | 环境配置 | `.env.dev` | VERIFIED | dev 配置加载通过 |
| `.env.test` | 环境配置 | `.env.test` | VERIFIED | 测试环境可选择 |
| `.env.pro` | 环境配置 | `.env.pro` | VERIFIED | 生产环境可选择 |
| `config/__init__.py` | 配置包 | `config/__init__.py` | VERIFIED | 导入通过 |
| `config/load_env.py` | 环境与日志 | `config/load_env.py` | VERIFIED | 环境选择和日志降级通过 |
| `config/logging.conf` | 日志 | `config/logging.conf` | VERIFIED | 控制台和文件日志通过 |
| `constants/__init__.py` | 常量包 | `constants/__init__.py` | VERIFIED | 导入通过 |
| `constants/code_enum.py` | 系统常量 | `constants/code_enum.py` | VERIFIED | 枚举测试通过 |
| `constants/dify_rest_api.py` | Dify URL | `constants/dify_rest_api.py` | VERIFIED | URL 测试通过 |
```

将功能覆盖表中的第 1 层改为 `VERIFIED`。

## 12. 提交

```powershell
git add .
git commit -m "feat: implement environment logging and constants"
git status
```

最终 `git status` 应为：

```text
nothing to commit, working tree clean
```

## 13. 常见故障

### 找不到 `uv`

安装 uv 后重新打开 PowerShell，并执行：

```powershell
uv --version
```

### PowerShell 禁止激活脚本

可以不激活，直接使用：

```powershell
uv run python --version
uv run python -c "from config.load_env import load_env; load_env()"
```

### `logs/assistant.log` 创建失败

确认命令是在复刻项目根目录执行，并确认 `config/logging.conf` 存在。

### 控制台没有颜色

验证：

```powershell
python -c "import colorlog; print(colorlog.__version__)"
```

没有颜色不影响文件日志和本层功能。
