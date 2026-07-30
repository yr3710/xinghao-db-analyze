# Aix-DB 功能全覆盖复刻：第 03 层

## Vue 3 基础框架

## 1. 本层目标

建立可运行的前端基础链路：

```text
Browser
→ Vite
→ Vue 3
→ Vue Router
→ Pinia
→ Naive UI
→ Vite /sanic Proxy
→ Sanic /system/health
```

同时接入 UnoCSS、自动导入、全局 SCSS、开发代理和生产分包。

## 2. 文件范围

```text
web/
├── index.html
├── package.json
├── pnpm-lock.yaml
├── tsconfig.json
├── uno.config.ts
├── vite.config.ts
├── auto-imports.d.ts
├── components.d.ts
├── public/
│   └── runtime-config.js
└── src/
    ├── App.vue
    ├── NaiveProvider.vue
    ├── env.d.ts
    ├── main.ts
    ├── shims-vue.d.ts
    ├── assets/svg/
    ├── router/index.ts
    ├── store/index.ts
    ├── styles/
    │   ├── global.scss
    │   ├── index.scss
    │   ├── markdown.scss
    │   ├── naive-variables.scss
    │   ├── theme.scss
    │   └── typography.scss
    └── views/home.vue
```

其中 `App.vue`、`main.ts`、`NaiveProvider.vue`、Router、Store 和 `home.vue` 是当前依赖闭包下的功能脚手架，后续业务层会逐步替换为原项目实现。

## 3. 前端环境

检查：

```powershell
node --version
pnpm --version
```

要求：

```text
Node >= 18.12
pnpm >= 9
```

按照原项目手敲 `web/package.json`，然后安装：

```powershell
cd D:\PycharmProjects\PersonCoding\xinghao-db-analyze\web
pnpm install
```

检查核心依赖：

```powershell
pnpm list vue
pnpm list vite
pnpm list pinia
pnpm list vue-router
pnpm list naive-ui
pnpm list unocss
```

## 4. 浏览器入口

按照原项目复刻：

- `index.html`
- `tsconfig.json`
- `src/env.d.ts`
- `src/shims-vue.d.ts`
- `public/runtime-config.js`

运行时配置初始化为：

```javascript
window.__AIX_RUNTIME_CONFIG__
  = window.__AIX_RUNTIME_CONFIG__ || {}
```

图片和 SVG 属于资源文件，最终等价审计时进行文件级同步，不需要手敲二进制。

## 5. Vue 插件骨架

当前版本需要安装：

- Vue 应用；
- Vue Router；
- Pinia；
- Naive UI Provider；
- 根路由；
- 后端健康检查页面。

当前健康检查请求：

```typescript
fetch('/sanic/system/health')
```

其真实路径：

```text
/sanic/system/health
→ Vite Proxy 删除 /sanic
→ http://localhost:8088/system/health
```

## 6. UnoCSS 和自动导入

按照原源码复刻 `uno.config.ts`。

Vite 插件必须包含：

```text
UnoCSS
Vue
Markdown Raw
Vue JSX
AutoImport
Components
Icons
```

`main.ts` 必须导入：

```typescript
import 'virtual:uno.css'
```

运行 Vite 后应生成：

```text
auto-imports.d.ts
components.d.ts
.eslintrc-auto-import.json
```

这些属于生成文件，不需要手敲。

## 7. 全局样式

按照原源码复刻六个 SCSS 文件，并在 `App.vue` 引入：

```vue
<style lang="scss">
@use '@/styles/index.scss';
</style>
```

Vite 配置需要向每个 SCSS 文件注入：

```typescript
css: {
  preprocessorOptions: {
    scss: {
      additionalData: `
        @use '@/styles/naive-variables.scss' as *;
      `,
    },
  },
},
```

## 8. 完整 Vite 配置

最终 `vite.config.ts` 应与原项目一致，覆盖：

- 根目录 PageAgent 构建变量读取；
- `/sanic` 等全部开发代理；
- 自动导入；
- Naive UI Resolver；
- 图标加载；
- Markdown Raw；
- `@` 路径别名；
- 构建变量；
- Rollup 警告过滤；
- 第三方依赖手动分包；
- SCSS 变量注入。

## 9. 运行验证

终端一：

```powershell
cd D:\PycharmProjects\PersonCoding\xinghao-db-analyze
python serv.py
```

终端二：

```powershell
cd D:\PycharmProjects\PersonCoding\xinghao-db-analyze\web
pnpm dev
```

浏览器访问：

```text
http://localhost:2048
```

必须显示：

```text
Aix-DB：running
```

确认：

- 页面由 Naive UI 渲染；
- Router 正常；
- UnoCSS 原子样式生效；
- 全局字体和主题生效；
- 点击检查按钮能够再次请求后端；
- Browser Console 没有错误。

## 10. 生产构建

```powershell
pnpm build
```

2026-07-30 实际验收结果：

```text
Vite 6.4.3
2813 modules transformed
build completed successfully
```

构建生成了：

```text
dist/assets/vue-core-*.js
dist/assets/naive-ui-*.js
dist/assets/vendor-*.js
dist/assets/home-*.js
dist/assets/index-*.css
```

说明生产分包配置真实生效。

## 11. 完成标准

- `pnpm install` 成功；
- Vue 页面可以访问；
- Router 根路由正常；
- Pinia 安装正常；
- Naive UI 正常渲染；
- UnoCSS 生效；
- `/sanic` 代理连接后端；
- 六个 SCSS 文件进入构建；
- 自动导入类型文件生成；
- `pnpm build` 通过；
- 生产包完成分块。

## 12. 覆盖状态

标记为 `VERIFIED`：

```text
web/package.json
web/index.html
web/tsconfig.json
web/uno.config.ts
web/vite.config.ts
web/public/runtime-config.js
web/src/env.d.ts
web/src/shims-vue.d.ts
web/src/styles/*.scss
```

标记为 `GENERATED`：

```text
web/pnpm-lock.yaml
web/auto-imports.d.ts
web/components.d.ts
web/.eslintrc-auto-import.json
web/dist/*
```

标记为 `TEMP`：

```text
web/src/App.vue
web/src/main.ts
web/src/NaiveProvider.vue
web/src/router/index.ts
web/src/store/index.ts
web/src/views/home.vue
```

## 13. 提交前检查

```powershell
git diff --cached --name-only
git status --short
```

不要将尚未完成的后端 `common/llm_util.py` 混入前端提交。

提交第 3 层：

```powershell
git add web
git diff --cached --name-only
git commit -m "feat: complete Vue application foundation"
git status
```

