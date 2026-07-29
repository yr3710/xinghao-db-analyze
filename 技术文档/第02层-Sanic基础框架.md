# Aix-DB 功能全覆盖复刻：第 02 层

## Sanic 基础框架、自动路由、统一响应、参数解析与 JWT

## 1. 本层目标

完成后，复刻项目应当具备：

- Sanic 应用启动入口；
- 单进程和多 Worker 配置；
- Worker 启动超时和请求超时配置；
- Sanic Extensions 和 OpenAPI 页面；
- Controller 包递归扫描；
- Blueprint 自动注册；
- 自定义业务异常；
- 统一 JSON 响应；
- 特殊数据类型 JSON 序列化；
- Pydantic Body 自动校验；
- Query、Form 和 Path 参数转换；
- JWT 校验；
- 启动阶段 MinIO 初始化失败时不阻断服务。

## 2. 本层文件

```text
Aix-DB-Replica/
├── serv.py
├── common/
│   ├── __init__.py
│   ├── exception.py
│   ├── param_parser.py
│   ├── res_decorator.py
│   ├── route_utility.py
│   └── token_decorator.py
├── controllers/
│   ├── __init__.py
│   └── health_api.py
└── docs/
    ├── redoc.html
    └── swagger.html
```

`controllers/health_api.py` 是复刻过程的临时测试脚手架，不属于原项目一方源码，后续真实 Controller 接入后删除。

## 4. 实现顺序

### 4.1 自定义异常

完整手敲 `common/exception.py`，实现：

- 从 `SysCodeEnum` 读取状态码；
- 支持覆盖默认错误消息；
- `__str__()`；
- `to_dict()`。

验证：

```powershell
python -c "from common.exception import MyException; from constants.code_enum import SysCodeEnum; e=MyException(SysCodeEnum.PARAM_ERROR, '缺少名称'); print(e); print(e.to_dict())"
```

预期：

```text
MyException: code: 400, message: 缺少名称
{'code': 400, 'message': '缺少名称'}
```

### 4.2 Blueprint 自动发现

完整手敲 `common/route_utility.py`。调用链：

```text
autodiscover(app, controllers, recursive=True)
→ 递归扫描 Python 文件
→ importlib 动态导入
→ inspect 查找 Blueprint
→ app.blueprint(bp)
```

### 4.3 OpenAPI 静态页面

创建 `docs` 目录，完整手敲：

```text
docs/redoc.html
docs/swagger.html
```

这两个文件必须在调用 `app.extend()` 之前存在，否则 Sanic Extensions 初始化时会抛出 `FileNotFoundError`。

### 4.4 Sanic 入口

完整手敲 `serv.py`，保留：

- `KMP_DUPLICATE_LIB_OK`；
- `WorkerManager.THRESHOLD`；
- `load_env()`；
- `configure_logging=False`；
- `before_server_start`；
- `main_process_start`；
- `autodiscover()`；
- SSE 相关超时；
- OpenAPI 配置；
- `/` 空响应；
- `get_server_config()`；
- `app.run()`。

当前尚未复刻 `common/minio_util.py`，启动日志中出现 MinIO 初始化失败属于预期警告。

### 4.5 统一 JSON 响应

完整手敲 `common/res_decorator.py`，实现：

```text
CustomJSONEncoder
async_json_resp
```

Encoder 需要覆盖日期、时间、Decimal、bytes、Pydantic、NumPy 和其他具有 `tolist()` 的对象。

响应装饰器需要覆盖：

- 正常返回；
- `MyException`；
- 未知异常；
- 请求和响应日志。

### 4.6 自动参数解析

完整手敲 `common/param_parser.py`，保留：

- `parse_params`；
- `_parse_body`；
- `_parse_query_or_form`；
- `_convert_type`；
- `parse_body`；
- `parse_query`；
- `parse_form`。

### 4.7 JWT

完整手敲 `common/token_decorator.py`，覆盖：

- 缺少 Token；
- `Bearer` 前缀；
- HS256 解码；
- Token 过期；
- 无效 Token；
- Payload 写入 `request.ctx.user_payload`。

开发默认密钥：

```text
550e8400-e29b-41d4-a716-446655440000
```

生产环境必须通过 `JWT_SECRET_KEY` 替换。

## 5. 临时验收 Blueprint

`controllers/health_api.py` 提供：

```text
GET  /system/health
POST /system/echo
GET  /system/add
GET  /system/protected
```

分别验证：

- Blueprint 自动发现和统一响应；
- Pydantic Body；
- 查询参数类型转换；
- JWT 鉴权。

## 6. 静态检查

从复刻项目根目录执行：

```powershell
python -m compileall common config constants controllers
python -m py_compile serv.py
```

必须没有 SyntaxError。

## 7. 启动验收

```powershell
$env:PYTHONUTF8=1
python serv.py
```

后端应监听：

```text
http://localhost:8088
```

MinIO 尚未实现时允许出现警告，但 Sanic 必须继续启动。

## 8. 接口验收

另开 PowerShell。

### 8.1 根接口

```powershell
curl.exe -i http://localhost:8088/
```

预期：

```text
HTTP/1.1 204 No Content
```

### 8.2 健康检查

```powershell
curl.exe http://localhost:8088/system/health
```

预期：

```json
{"code":200,"msg":"ok","data":{"name":"Aix-DB","status":"running"}}
```

### 8.3 正确 Body

```powershell
curl.exe -X POST http://localhost:8088/system/echo `
  -H "Content-Type: application/json" `
  --data-raw '{"query":"查询销售额","count":2}'
```

预期 `code` 为 `200`，`count` 为数字 `2`。

### 8.4 错误 Body

```powershell
curl.exe -X POST http://localhost:8088/system/echo `
  -H "Content-Type: application/json" `
  --data-raw '{"query":"测试","count":"错误"}'
```

预期 `code` 为 `400`，并返回参数验证错误。

### 8.5 Query 类型转换

```powershell
curl.exe "http://localhost:8088/system/add?number_a=10&number_b=20"
```

预期 `data.result` 为数字 `30`。

### 8.6 缺少 Token

```powershell
curl.exe -i http://localhost:8088/system/protected
```

预期 HTTP 状态为 `401`。

### 8.7 有效 Token

```powershell
$token = python -c "import jwt; from datetime import datetime, timedelta; payload={'id':1,'username':'admin','exp':datetime.utcnow()+timedelta(hours=1)}; print(jwt.encode(payload,'550e8400-e29b-41d4-a716-446655440000',algorithm='HS256'))"

curl.exe http://localhost:8088/system/protected `
  -H "Authorization: Bearer $token"
```

预期：

- `code` 为 `200`；
- `data.message` 为“鉴权成功”；
- `data.user.id` 为 `1`。

### 8.8 过期 Token

```powershell
$expiredToken = python -c "import jwt; from datetime import datetime, timedelta; payload={'id':1,'exp':datetime.utcnow()-timedelta(hours=1)}; print(jwt.encode(payload,'550e8400-e29b-41d4-a716-446655440000',algorithm='HS256'))"

curl.exe -i http://localhost:8088/system/protected `
  -H "Authorization: Bearer $expiredToken"
```

预期 HTTP 状态为 `401`，消息为“Token已过期”。

## 9. 文档和日志验收

浏览器访问：

```text
http://localhost:8088/docs/swagger
http://localhost:8088/docs/redoc
```

检查日志：

```powershell
Get-Content logs\assistant.log -Tail 20
```

请求日志应包含 Path、Method、Params、JSON Body 和 Response。

## 10. 覆盖表

```markdown
| `serv.py` | Sanic 入口 | `serv.py` | VERIFIED | 启动及根接口通过 |
| `common/__init__.py` | 公共包 | `common/__init__.py` | VERIFIED | 导入通过 |
| `common/exception.py` | 业务异常 | `common/exception.py` | VERIFIED | 异常转换通过 |
| `common/param_parser.py` | 参数解析 | `common/param_parser.py` | VERIFIED | Body 和 Query 通过 |
| `common/res_decorator.py` | 统一响应 | `common/res_decorator.py` | VERIFIED | 三类响应通过 |
| `common/route_utility.py` | 路由发现 | `common/route_utility.py` | VERIFIED | Blueprint 自动注册通过 |
| `common/token_decorator.py` | JWT | `common/token_decorator.py` | VERIFIED | 三种 Token 路径通过 |
| `controllers/__init__.py` | Controller 包 | `controllers/__init__.py` | VERIFIED | 自动扫描通过 |
| `docs/redoc.html` | OpenAPI | `docs/redoc.html` | VERIFIED | 页面可访问 |
| `docs/swagger.html` | OpenAPI | `docs/swagger.html` | VERIFIED | 页面可访问 |
| `controllers/health_api.py` | 临时脚手架 | `controllers/health_api.py` | TEMP | 真实 Controller 接入后删除 |
```

将第 2 层改为 `VERIFIED`。

## 11. 提交

先停止服务器：

```text
Ctrl+C
```

提交：

```powershell
git add .
git commit -m "feat: implement Sanic application foundation"
git status
```

`git status` 最终应为：

```text
nothing to commit, working tree clean
```

## 12. 本层调用图

```text
HTTP Request
→ Sanic Router
→ 自动发现的 Blueprint
→ check_token
→ async_json_resp
→ parse_params
→ Handler
→ 统一 JSON Response
→ 请求日志
```

