# 第 0 层技术方案：空项目初始化与 Sanic 服务启动

## 1. 阶段目标

将一个空目录初始化为具备以下能力的 Python 后端项目：

- 使用 Python 3.11 作为运行环境
- 使用 `uv` 管理虚拟环境和项目依赖
- 使用 `pyproject.toml` 描述项目
- 根据 `APP_ENV` 加载环境变量文件
- 启动 Sanic HTTP 服务
- 提供根接口和健康检查接口

本阶段不实现 LLM、SSE、数据库、用户认证和前端。

## 2. 技术选型

| 技术 | 作用 |
|---|---|
| Python 3.11 | 项目运行时 |
| uv | 虚拟环境、依赖和锁文件管理 |
| Sanic | 异步 HTTP 服务 |
| sanic-ext | 后续 OpenAPI 和参数校验扩展 |
| python-dotenv | 从 `.env.*` 文件加载环境变量 |

版本范围与原 Aix-DB 项目保持兼容。

## 3. 目录结构

```text
Aix-DB-Copy/
├── common/
│   └── __init__.py
├── config/
│   ├── __init__.py
│   └── load_env.py
├── controllers/
│   └── __init__.py
├── services/
│   └── __init__.py
├── tests/
│   └── __init__.py
├── .env.dev
├── .gitignore
├── pyproject.toml
└── serv.py
```

`__init__.py` 用于将目录声明为 Python 包，本阶段保持为空。

## 4. 项目配置

### 4.1 `pyproject.toml`

```toml
[project]
name = "aix-db-copy"
version = "0.1.0"
description = "A functional rebuild of Aix-DB"
requires-python = ">=3.11,<3.12"

dependencies = [
    "sanic>=25.0.0,<25.4.0",
    "sanic-ext>=24.0.0,<=24.12.0",
    "python-dotenv>=1.0.1,<2.0.0",
]

[tool.black]
line-length = 88
target-version = ["py311"]
```

### 4.2 `.gitignore`

```gitignore
.venv/
.idea/
__pycache__/
*.py[cod]
.env
.env.*
!.env.example
logs/
dist/
build/
```

从第 1 层开始，`.env.dev` 会保存 LLM API Key，因此必须忽略所有 `.env.*`。可以提交不含密钥的 `.env.example`。

### 4.3 `.env.dev`

```dotenv
APP_ENV=dev

SERVER_HOST=0.0.0.0
SERVER_PORT=8088
SERVER_WORKERS=1
```

## 5. 环境变量加载

`config/load_env.py`：

```python
import os
from pathlib import Path

from dotenv import load_dotenv


def load_env() -> None:
    project_root = Path(__file__).resolve().parent.parent
    app_env = os.getenv("APP_ENV", "dev")
    env_file = project_root / f".env.{app_env}"

    if not env_file.exists():
        raise FileNotFoundError(f"Environment file not found: {env_file}")

    load_dotenv(env_file, override=True)
```

加载过程：

```text
serv.py
  → load_env()
  → 计算项目根目录
  → 读取 APP_ENV，默认使用 dev
  → 定位 .env.dev
  → 将配置写入 os.environ
```

`override=True` 表示环境文件中的值可以覆盖进程中已有的同名变量。生产环境应根据部署策略决定是否允许覆盖。

## 6. Sanic 服务入口

`serv.py`：

```python
import os

from sanic import Sanic
from sanic.response import json

from config.load_env import load_env


load_env()

app = Sanic("Aix-DB-Copy")


@app.get("/")
async def index(request):
    return json(
        {
            "name": "Aix-DB-Copy",
            "status": "running",
            "environment": os.getenv("APP_ENV"),
        }
    )


@app.get("/health")
async def health(request):
    return json({"healthy": True})


def get_server_config() -> dict:
    return {
        "host": os.getenv("SERVER_HOST", "0.0.0.0"),
        "port": int(os.getenv("SERVER_PORT", "8088")),
        "single_process": True,
        "auto_reload": False,
    }


if __name__ == "__main__":
    server_config = get_server_config()
    app.run(**server_config)
```

运行链路：

```text
执行 serv.py
  → 加载 .env.dev
  → 创建 Sanic 应用
  → 注册 / 和 /health
  → 读取服务器配置
  → app.run()
```

开发阶段使用 `single_process=True`，减少多进程对调试的干扰。后续部署阶段再恢复原项目的 Worker 配置。

## 7. 初始化与启动

```powershell
py -3.11 --version
uv venv --python 3.11
uv sync
uv run python serv.py
```

服务默认监听：

```text
http://localhost:8088
```

## 8. 验收方案

根接口：

```powershell
Invoke-RestMethod http://localhost:8088
```

预期：

```text
name        : Aix-DB-Copy
status      : running
environment : dev
```

健康检查：

```powershell
Invoke-RestMethod http://localhost:8088/health
```

预期：

```text
healthy
-------
True
```

语法检查：

```powershell
uv run python -m compileall .
```

## 9. 常见故障

### 找不到 Python 3.11

```powershell
py -0p
```

检查已安装的 Python 解释器，并在安装 Python 3.11 后重新创建虚拟环境。

### PowerShell 禁止激活脚本

不必修改全局执行策略，可以直接执行：

```powershell
uv run python serv.py
```
或者对当前 PowerShell 会话临时放宽限制：

```powershell
 Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 找不到 `.env.dev`

确认文件位于项目根目录，而不是 `config/` 中，并确认文件没有被保存成 `.env.dev.txt`。

### 8088 端口被占用

临时修改 `.env.dev`：

```dotenv
SERVER_PORT=8089
```

## 10. 阶段完成标准

- Python 版本为 3.11
- `.venv` 创建成功
- `uv sync` 安装成功
- `.env.dev` 加载成功
- Sanic 服务启动成功
- `/` 和 `/health` 返回预期内容
- 项目可通过 `compileall` 检查

## 11. 下一阶段

第 1 层将实现真实的流式 LLM 问答：

```text
POST /chat
  → Pydantic 请求校验
  → ChatService
  → OpenAI 兼容模型
  → SSE 流式响应
```

## 12. 参考资料

- [Sanic Getting Started](https://sanic.dev/en/guide/getting-started.html)
- [Sanic Running Guide](https://sanic.dev/en/guide/running/running.md)
- [python-dotenv](https://github.com/theskumar/python-dotenv)
- [uv Documentation](https://docs.astral.sh/uv/)
