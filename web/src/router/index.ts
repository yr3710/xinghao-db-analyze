import type { App } from 'vue'
import {
  createRouter,
  createWebHistory,
} from 'vue-router'
import { useUserStore } from '@/store/business/userStore'
import routes from './routes'

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局前置守卫
router.beforeEach((to, from, next) => {
    const userStore = useUserStore()
    if (to.meta.requiresAuth && !userStore.isLoggedIn) {
        // 如果目标路由需要认证且用户未登录，则重定向到登录页面
        next('/login')
    } else {
        next()
    }
})

export async function setupRouter(app: App) {
  app.use(router)
  await router.isReady()
}

export default router