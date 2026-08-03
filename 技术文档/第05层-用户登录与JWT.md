# Aix-DB 功能复刻：第 05 层——用户登录与 JWT

## 1. 本层目标

完成真实用户认证闭环：

```text
登录页面
  → Sanic /user/login
  → bcrypt 验证 t_user
  → 生成 JWT
  → Pinia 保存用户和角色
  → 路由守卫保护业务页面
  → 请求携带 Bearer Token
  → 退出后清除会话并返回登录页
```

## 2. 本层源码范围

```text
services/user_service.py
controllers/user_rest_api.py
web/src/store/business/userStore.ts
web/src/api/index.ts（本层先完成 login，聊天 API 后续补齐）
web/src/api/user.ts
web/src/views/auth/login.vue
web/src/views/user/user-manager.vue
web/src/components/IconifyIcon/index.vue
web/src/config/page-agent.ts
web/src/hooks/usePageAgent.ts
web/src/hooks/pageAgentInstructions.ts
```

本层仍使用临时路由和临时首页。源码中的侧边栏退出入口将在应用壳层复刻。

## 3. 后端执行顺序

1. 完整复刻 `services/user_service.py`。
2. 完整复刻 `controllers/user_rest_api.py`。
3. 确认 `TUser` 和用户相关 Schema 已存在。
4. 创建管理员测试数据。
5. 启动 Sanic。

管理员创建命令：

```powershell
uv run python -c "from config.load_env import load_env; load_env(); import asyncio; from services.user_service import add_user; asyncio.run(add_user('admin','123456','','admin'))"
```

启动后端：

```powershell
uv run python serv.py --env=dev
```

## 4. 后端登录验证

```powershell
$body = @{
    username = "admin"
    password = "123456"
} | ConvertTo-Json

$result = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8088/user/login" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body

$result.data.token
```

错误密码必须登录失败。

## 5. JWT 保护验证

```powershell
$headers = @{
    Authorization = "Bearer $($result.data.token)"
}

$listBody = @{
    page = 1
    size = 10
    name = ""
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8088/user/list" `
    -Method Post `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $listBody
```

缺少 Token、伪造 Token 和过期 Token 都必须返回 `401`。

## 6. 前端状态验证

源码版 `userStore` 使用 `sessionStorage`：

```javascript
JSON.parse(sessionStorage.getItem('user')).token
```

管理员 JWT 应使以下 Getter 成立：

```text
isLoggedIn = true
isAdmin = true
role = admin
```

刷新当前标签页后登录状态应恢复。

## 7. 路由规则

登录路由必须公开：

```ts
{
  path: '/login',
  name: 'Login',
  component: () => import('@/views/auth/login.vue'),
}
```

业务路由配置：

```ts
meta: {
  requiresAuth: true,
}
```

守卫规则：

```ts
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()

  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    next('/login')
  } else {
    next()
  }
})
```

`userStore.init()` 必须在路由开始处理受保护页面前执行。

## 8. 用户管理验证

访问：

```text
http://localhost:2048/user-manager
```

依次验证：

1. 查询管理员。
2. 按用户名搜索。
3. 新增 `replica_test`。
4. 使用新用户密码登录。
5. 编辑手机号且不修改密码。
6. 修改密码并使用新密码登录。
7. 删除测试用户。
8. 密码在数据库中以 `$2b$12$...` 保存。

不要删除当前使用的管理员。

## 9. 退出登录验证

核心源码逻辑：

```ts
const handleLogout = () => {
  userStore.logout()
  setTimeout(() => {
    router.replace('/login')
  }, 100)
}
```

退出后必须满足：

```text
userStore.user = null
userStore.role = user
sessionStorage 中不存在 user
当前页面为 /login
重新访问业务路由仍会返回 /login
```

本阶段可以暂时把按钮放在 `TEMP` 首页；复刻源码 SideBar 后删除。

## 10. 构建验收

```powershell
cd web
pnpm build
```

构建退出码必须为 `0`。

## 11. 覆盖判定

```md
| web/src/store/business/userStore.ts | JWT状态与角色 | VERIFIED |
| web/src/views/auth/login.vue | 登录页面 | VERIFIED |
| web/src/api/user.ts | 用户管理API | VERIFIED |
| web/src/views/user/user-manager.vue | 用户管理页面 | VERIFIED |
| web/src/components/IconifyIcon/index.vue | 图标组件 | VERIFIED |
| web/src/config/page-agent.ts | Page Agent开关 | VERIFIED |
| web/src/api/index.ts | 登录与聊天综合API | CODING |
| web/src/hooks/usePageAgent.ts | 页面代理 | RUNNING |
| web/src/hooks/pageAgentInstructions.ts | 页面代理指令 | RUNNING |
| services/user_service.py | 用户与问答记录服务 | RUNNING |
| controllers/user_rest_api.py | 用户与问答记录API | RUNNING |
```

`user_service.py`、`user_rest_api.py` 和 `api/index.ts` 中的问答记录功能将在聊天层继续验证，不能提前标记整文件 `VERIFIED`。

## 12. 本层验收清单

- [ ] 正确密码登录成功。
- [ ] 错误密码登录失败。
- [ ] JWT 包含用户 ID、用户名、角色和过期时间。
- [ ] 管理员角色解析正确。
- [ ] 刷新后会话恢复。
- [ ] 未登录访问业务页面跳转登录页。
- [ ] 用户增删改查真实写入数据库。
- [ ] 密码使用 bcrypt 保存。
- [ ] 退出登录清除 Store 和 `sessionStorage`。
- [ ] 退出后不能直接访问受保护页面。
- [ ] `pnpm build` 成功。

完成后继续应用布局壳、导航和正式退出入口。
