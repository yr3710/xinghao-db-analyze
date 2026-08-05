# Aix-DB 功能复刻：第 10 层——Schema 浏览

## 1. 本层目标

完成数据源 Schema 浏览闭环：

```text
连接配置
  → 测试数据库连接
  → 读取数据库表列表
  → 用户选择需要管理的表
  → 同步表和字段元数据
  → 写入 t_datasource_table / t_datasource_field
  → 浏览已同步的表和字段
  → 编辑自定义注释与启用状态
```

本层只处理数据库结构元数据，不查询业务数据。

## 2. 本层源码范围

```text
common/datasource_util.py
services/datasource_service.py
controllers/datasource_api.py
model/schemas.py（复用已有 Schema）
web/src/api/datasource.ts
web/src/components/datasource/datasource-form.vue
web/src/views/datasource/datasource-manager.vue
web/src/views/datasource/datasource-table-list.vue
web/src/router/routes.ts
tests/test_datasource_management.py
```

本层没有新增数据库模型或迁移，直接使用已有的 `DatasourceTable` 和 `DatasourceField`。

## 3. 后端执行顺序

1. 在 `DatasourceConnectionUtil` 中复刻表和字段元数据查询。
2. 根据数据库类型选择 SQLAlchemy 或原生驱动。
3. 将不同数据库的返回结果转换成统一结构。
4. 在 `DatasourceService` 中实现表字段同步和本地元数据查询。
5. 保留原项目的新增、更新、清理和 `num` 统计规则。
6. 在数据源控制器中开放七个 Schema 接口。
7. 同步接口保留管理员权限检查，其余接口沿用项目现有认证边界。

## 4. 多数据库 Schema 兼容矩阵

| 类型代码 | 数据库 | 表元数据来源 | 字段元数据来源 | 连接方式 |
|---|---|---|---|---|
| `mysql` | MySQL | `information_schema.TABLES` | `INFORMATION_SCHEMA.COLUMNS` | SQLAlchemy |
| `pg` | PostgreSQL | `pg_class / pg_namespace` | `pg_attribute` | SQLAlchemy |
| `oracle` | Oracle | `ALL_TABLES / ALL_VIEWS / ALL_MVIEWS` | `ALL_TAB_COLUMNS` | SQLAlchemy |
| `sqlServer` | SQL Server | `INFORMATION_SCHEMA.TABLES` | `INFORMATION_SCHEMA.COLUMNS` | SQLAlchemy |
| `ck` | ClickHouse | `system.tables` | `system.columns` | SQLAlchemy |
| `dm` | 达梦 | `all_tab_comments` | `ALL_TAB_COLS` | `dmPython` |
| `doris` | Apache Doris | `information_schema.TABLES` | `INFORMATION_SCHEMA.COLUMNS` | PyMySQL |
| `starrocks` | StarRocks | `information_schema.TABLES` | `INFORMATION_SCHEMA.COLUMNS` | PyMySQL |
| `redshift` | AWS Redshift | `pg_class` | `pg_attribute` | `redshift_connector` |
| `kingbase` | Kingbase | PostgreSQL 系统目录 | PostgreSQL 系统目录 | psycopg2 |
| `es` | Elasticsearch | 索引列表和 Mapping `_meta` | Mapping `properties` | Elasticsearch Client |

统一表返回结构：

```json
{
  "tableName": "users",
  "tableComment": "用户表"
}
```

统一字段返回结构：

```json
{
  "fieldName": "id",
  "fieldType": "bigint",
  "fieldComment": "主键",
  "fieldIndex": 0
}
```

## 5. 表字段同步规则

调用 `sync_tables()` 后按以下顺序处理：

1. 根据数据源 ID 查询 `Datasource`。
2. 解密数据源连接配置。
3. 查询源数据库总表数。
4. 根据 `ds_id + table_name` 新增或更新本地表记录。
5. 根据 `table_id + field_name` 新增或更新本地字段记录。
6. 新记录使用数据库原始注释初始化 `custom_comment`。
7. 已存在的 `custom_comment` 不被新的数据库注释覆盖。
8. 按原项目规则删除非空保留列表之外的表和字段。
9. 更新 `Datasource.num` 为 `已选择表数/数据库总表数`。
10. 提交同步事务。

原项目边界被完整保留：

- 空的表 ID 保留列表不会触发表清理。
- 空的字段 ID 保留列表不会触发字段清理。
- 单张表字段读取失败时按空字段列表继续同步其他表。
- `save_table()` 只修改 `custom_comment` 和 `checked`。
- `save_field()` 只修改 `custom_comment` 和 `checked`。
- `is_select_all` 保留原接口参数，但不改变同步数据结果。

## 6. 后端接口

| 方法 | 路径 | 请求 | 返回数据 |
|---|---|---|---|
| POST | `/sanic/datasource/getTablesByConf` | `type, configuration` | 数据库表列表 |
| POST | `/sanic/datasource/getFieldsByConf` | `type, configuration, table_name` | 数据库字段列表 |
| POST | `/sanic/datasource/syncTables/{ds_id}` | `tables, is_select_all` | 同步结果 |
| POST | `/sanic/datasource/tableList/{ds_id}` | 无请求体 | 已同步表列表 |
| POST | `/sanic/datasource/fieldList/{table_id}` | 无请求体 | 已同步字段列表 |
| POST | `/sanic/datasource/saveTable` | `id, custom_comment, checked` | 保存结果 |
| POST | `/sanic/datasource/saveField` | `id, custom_comment, checked` | 保存结果 |

表列表使用数据库字段名：

```text
id, ds_id, table_name, table_comment, custom_comment, checked
```

字段列表使用数据库字段名：

```text
id, ds_id, table_id, field_name, field_type,
field_comment, custom_comment, field_index, checked
```

## 7. 前端操作流程

数据源表单改为两步：

```text
第一步：连接配置
  → 填写数据库连接
  → 测试连接
  → 读取表列表

第二步：选择表
  → 搜索表
  → 分批显示
  → 单选、当前页全选或全部全选
  → 保存数据源
  → 调用 syncTables 同步表字段
```

编辑已有数据源时，前端调用 `tableList` 恢复之前选中的表。

Schema 浏览路由：

```text
/datasource/table/:dsId/:dsName
```

Schema 页面左侧展示表搜索和表列表，右侧展示当前表信息及字段列表。页面支持：

- 切换当前表。
- 查看表和字段的数据库原始注释。
- 编辑表和字段的自定义注释。
- 启用或停用表。
- 启用或停用字段。

状态开关请求失败时，页面按原项目行为提示错误但不立即回滚开关；刷新后以服务端状态为准。本层不对该源码行为增加额外修复。

## 8. 手工验收步骤

1. 使用管理员账号进入数据源管理。
2. 新建一个可连接的数据源。
3. 点击“下一步”，确认可以读取数据库表列表。
4. 搜索并选择部分表后保存。
5. 确认数据源列表显示正确的 `selected/total`。
6. 点击数据源名称进入 Schema 页面。
7. 切换表并确认字段列表刷新。
8. 修改表自定义注释并刷新页面。
9. 修改字段自定义注释并刷新页面。
10. 切换表、字段启用状态并刷新页面。
11. 再次编辑数据源，确认历史表选择被恢复。

## 9. 自动化验证结果

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q common services controllers model
cd web
pnpm build
```

本层完成时结果：

```text
pytest: 63 passed, 1 skipped
Python compileall: PASSED
Vue production build: PASSED
```

跳过项为环境未提供真实 PostgreSQL 时的可选集成测试；11 种数据库 Schema 分支均有 Mock/分支测试。

## 10. 覆盖判定

| 模块 | 能力 | 状态 |
|---|---|---|
| `common/datasource_util.py` | 11 种数据库表字段读取 | VERIFIED |
| `services/datasource_service.py` | 同步、查询、编辑元数据 | VERIFIED |
| `controllers/datasource_api.py` | 七个 Schema API | VERIFIED |
| `web/src/components/datasource/datasource-form.vue` | 两步连接和表选择 | VERIFIED |
| `web/src/views/datasource/datasource-table-list.vue` | Schema 浏览和编辑 | VERIFIED |
| `web/src/router/routes.ts` | Schema 页面路由 | VERIFIED |
| `tests/test_datasource_management.py` | Schema 自动化测试 | VERIFIED |

## 11. 本层未实现范围

以下功能明确留到后续层：

- 数据内容预览。
- 任意 SQL 执行和 `execute_query()`。
- 表结构 Embedding 生成与更新。
- RAG 和向量检索。
- 表关系维护。
- Neo4j 和关系图。
- 字段数据映射。

本层没有为这些功能增加占位接口或临时实现。

## 12. 本层验收清单

- [x] 11 种数据库存在表查询分支。
- [x] 11 种数据库存在字段查询分支。
- [x] Elasticsearch 索引和 Mapping 可转换为统一元数据。
- [x] 表字段同步写入本地元数据表。
- [x] 重复同步保留自定义注释。
- [x] 数据源 `num` 更新为 `selected/total`。
- [x] 七个 Schema API 已注册。
- [x] 同步接口保留管理员权限检查。
- [x] 数据源表单支持连接配置和选择表两步流程。
- [x] Schema 页面支持表字段浏览和编辑。
- [x] 未引入数据预览、Embedding 或表关系。
- [x] 后端测试通过。
- [x] Python 编译通过。
- [x] 前端生产构建通过。
- [x] 未提交 Git 代码。
