# Aix-DB 功能复刻：第 04 层——模型配置与 LLM 接入

## 1. 本层目标

完成一条可运行的模型配置闭环：

```text
Vue 模型配置页
  → Sanic 模型配置 API
  → PostgreSQL t_ai_model
  → common.llm_util.get_llm()
  → ChatOllama / ChatOpenAI
  → 真实模型回复
```

本层完成后，应具备以下能力：

1. 创建和维护 AI 模型配置。
2. 检测模型服务是否可连接。
3. 设置唯一的默认 LLM。
4. 从数据库读取默认模型。
5. 创建 LangChain 模型客户端并发起真实对话。

## 2. 本层源码范围

### 2.1 数据模型

按以下顺序手敲：

```text
model/__init__.py
model/db_connection_pool.py
model/db_models.py
model/datasource_models.py
model/serializers.py
model/schemas.py
```

核心表为 `TAiModel`，对应数据库表 `t_ai_model`。

关键字段：

| 字段 | 含义 |
| --- | --- |
| `supplier` | 供应商，`3` 表示 Ollama |
| `model_type` | 模型类型，`1` 表示 LLM |
| `base_model` | 实际调用的模型名称 |
| `default_model` | 是否为默认模型 |
| `api_domain` | 模型服务地址 |
| `api_key` | API Key，本地 Ollama 可为空 |
| `protocol` | 接入协议，`2` 表示 Ollama |

### 2.2 后端模型配置

```text
services/aimodel_service.py
controllers/aimodel_api.py
```

职责划分：

- `aimodel_service.py`：数据库 CRUD、默认模型切换、连接检测、模型列表获取。
- `aimodel_api.py`：定义 Sanic 路由、读取参数、调用 Service、生成统一响应。

### 2.3 前端模型配置

```text
web/src/api/aimodel.ts
web/src/components/llm/llm-form.vue
web/src/views/system/config/llm-config.vue
web/src/NaiveProvider.vue
web/src/types/global.d.ts
```

另有一个跨层临时文件：

```text
web/src/store/business/userStore.ts
```

它只负责从 `localStorage` 提供开发 Token，状态必须记为 `TEMP`。第 5 层复刻正式用户系统时替换。

### 2.4 LLM 客户端工厂

```text
common/llm_util.py
```

它负责：

1. 查询默认 LLM。
2. 将 `supplier=3` 映射为 Ollama。
3. 将其他供应商统一映射为 OpenAI 兼容协议。
4. 延迟导入第三方模型客户端。
5. 应用温度、超时、最大 Token 和思考模式配置。
6. 保留 DeepSeek `reasoning_content`。

## 3. 启动基础依赖

### 3.1 PostgreSQL

首次创建容器：

```powershell
docker run -d `
  --name xinghao-db-postgres `
  -e POSTGRES_DB=xinghao_db `
  -e POSTGRES_USER=xinghao_db `
  -e POSTGRES_PASSWORD=1 `
  -p 15432:5432 `
  pgvector/pgvector:pg16
```

以后只需启动：

```powershell
docker start xinghao-db-postgres
```
删除容器：
```powershell
docker rm -f xinghao-db-postgres
```

查看所有容器：

```powershell
docker ps -a
```

验证：

```powershell
docker ps --filter name=xinghao-db-postgres
```

`.env.dev` 应包含：

```dotenv
SQLALCHEMY_DATABASE_URI=postgresql+psycopg2://xinghao_db:1@127.0.0.1:15432/xinghao_db
```

### 3.2 Ollama

验证已安装模型：

```powershell
ollama list
```

没有测试模型时执行：

```powershell
ollama pull qwen2.5:7b
```

验证服务：

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

## 4. 建表验证

项目启动时应执行模型元数据建表。启动后检查数据库中是否存在：

```text
t_ai_model
```

可以进入 PostgreSQL 容器检查：

```powershell
docker exec -it xinghao-db-postgres psql -U xinghao_db -d xinghao_db
```

在 `psql` 中执行：

```sql
\dt
\d t_ai_model
SELECT id, name, supplier, model_type, base_model, default_model
FROM t_ai_model
ORDER BY id;
```

退出：

```sql
\q
```

## 5. 启动项目

### 5.1 后端

在项目根目录执行：

```powershell
uv run python serv.py --env=dev
```

后端应正常连接 `15432` 端口的 PostgreSQL，且不能出现建表或导入错误。

### 5.2 前端

新开 PowerShell：

```powershell
cd web
pnpm dev
```

访问：

```text
http://localhost:2048/llm-config
```

## 6. 开发 Token

正式登录系统尚未进入复刻范围，因此临时把开发 JWT 放进浏览器的当前站点存储。

在浏览器开发者工具 Console 中执行：

```javascript
localStorage.setItem('token', '替换为开发JWT')
location.reload()
```

检查：

```javascript
localStorage.getItem('token')
```

这不是 PowerShell 命令，只能在浏览器 Console 中执行。

## 7. 创建本地模型配置

在模型配置页面新增：

```text
名称：本地 Qwen
模型类型：LLM
供应商：Ollama
协议：Ollama
基础模型：qwen2.5:7b
API 地址：http://127.0.0.1:11434
API Key：留空
```

验证顺序：

1. 点击连接检测，提示连接成功。
2. 保存模型。
3. 刷新页面后数据仍然存在。
4. 编辑并重新保存。
5. 设置为默认模型。
6. 默认标记正确显示。
7. 默认模型不能被删除。
8. 非默认模型能够删除。

## 8. API 验收

在浏览器 Network 面板中检查模型请求。

应满足：

1. 请求地址经过 `/sanic/system/aimodel`。
2. 请求携带开发 Token。
3. HTTP 状态码正常。
4. 响应符合项目统一响应结构。
5. 新增、修改和默认状态与数据库一致。

如果返回 `401`，依次检查：

```text
localStorage 是否存在 token
→ 页面是否刷新
→ userStore.getUserToken() 是否返回 token
→ Authorization 请求头是否出现
→ JWT 是否过期
```

## 9. 默认 LLM 工厂验收

`common.llm_util` 在导入时立即取得数据库连接池。因此独立验证时，必须先加载 `.env.dev`，再导入 `get_llm`。

### 9.1 创建客户端

```powershell
uv run python -c "from config.load_env import load_env; load_env(); from common.llm_util import get_llm; llm=get_llm(temperature=0); print(type(llm)); print(llm.model)"
```

Ollama 配置的预期结果：

```text
langchain_ollama.chat_models.ChatOllama
qwen2.5:7b
```

### 9.2 真实调用

```powershell
uv run python -c "from config.load_env import load_env; load_env(); from common.llm_util import get_llm; llm=get_llm(temperature=0, timeout=120); result=llm.invoke('只回复：Aix-DB模型调用成功'); print(result.content)"
```

应得到真实模型回复。只创建客户端而没有执行 `invoke`，不能算本层完全验收。

### 9.3 默认模型保护

当数据库中没有默认 LLM 时，`get_llm()` 应抛出：

```text
ValueError: No default AI model configured in database.
```

随后重新设置默认模型，再次调用应恢复成功。

## 10. 前端构建验收

```powershell
cd web
pnpm build
```

构建必须退出码为 `0`，不能只以开发服务器能打开作为通过依据。

## 11. 常见问题

### 数据库连接到了 5432

原因通常是先导入了数据库模块，后调用 `load_env()`，连接池已经使用默认地址初始化。

正确顺序：

```python
from config.load_env import load_env

load_env()

from common.llm_util import get_llm
```

### Ollama 检测成功，但真实调用找不到模型

检查数据库的 `base_model` 是否与 `ollama list` 中的名称完全一致，包括标签。

### 页面请求没有 Token

写入 `localStorage` 后刷新页面，使临时 Store 重新读取 Token。

### 页面提示对象不存在

检查 `NaiveProvider.vue` 是否已经换成源码版本，以及 `App.vue` 是否用它包裹路由出口。

### 找不到默认模型

检查：

```sql
SELECT id, name, model_type, default_model
FROM t_ai_model
WHERE model_type = 1;
```

必须有且只有一个默认 LLM。

## 12. 覆盖表

本层全部通过后，在 `REPLICATION-COVERAGE.md` 中记录：

```md
| model/__init__.py | Model 包初始化 | VERIFIED |
| model/db_connection_pool.py | SQLAlchemy 连接池 | VERIFIED |
| model/db_models.py | 数据库 ORM 模型 | VERIFIED |
| model/datasource_models.py | 数据源结构模型 | VERIFIED |
| model/serializers.py | ORM 序列化 | VERIFIED |
| model/schemas.py | 请求响应 Schema | VERIFIED |
| services/aimodel_service.py | 模型配置业务服务 | VERIFIED |
| controllers/aimodel_api.py | 模型配置 API | VERIFIED |
| web/src/api/aimodel.ts | 模型配置前端 API | VERIFIED |
| web/src/components/llm/llm-form.vue | 模型配置表单 | VERIFIED |
| web/src/views/system/config/llm-config.vue | 模型配置页面 | VERIFIED |
| web/src/NaiveProvider.vue | Naive UI 全局工具 | VERIFIED |
| web/src/types/global.d.ts | Window 全局类型 | VERIFIED |
| common/llm_util.py | 默认 LLM 工厂 | VERIFIED |
| web/src/store/business/userStore.ts | 第 5 层前的开发 Token Store | TEMP |
```

## 13. 本层通过标准

以下条件必须全部满足：

- [ ] PostgreSQL 可启动并存在 `t_ai_model`。
- [ ] 模型配置 CRUD 可以真实读写数据库。
- [ ] Ollama 连接检测成功。
- [ ] 模型可以设为默认。
- [ ] 默认模型不能被删除。
- [ ] 页面刷新后配置不丢失。
- [ ] `get_llm()` 返回正确客户端。
- [ ] `llm.invoke()` 获得真实回复。
- [ ] `pnpm build` 成功。
- [ ] 源码覆盖表已更新。
- [ ] 仅临时 `userStore.ts` 保持 `TEMP`。

全部勾选后，第 04 层状态才能记为：

```text
VERIFIED
```

下一层进入用户、JWT、Pinia 用户状态和登录界面，将替换本层的临时 Token Store。
