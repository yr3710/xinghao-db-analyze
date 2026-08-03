import type {App} from 'vue'
import {
    createRouter,
    createWebHistory,
} from 'vue-router'


const router = createRouter({
    history: createWebHistory(),

    routes: [
        {
            path: '/',
            name: 'Home',
            component: () => import(
                '@/views/home.vue'
                ),
            meta: {requiresAuth: true}, // 标记需要认证
        },
        {
            path: '/llm-config',
            name: 'LLMConfig',
            component: () => import('@/views/system/config/llm-config.vue'),
            meta: {requiresAuth: true}, // 标记需要认证
        },
        {
            path: '/login',
            name: 'Login',
            component: () => import('@/views/auth/login.vue'),
        },
        {
            path: '/user-manager',
            name: 'UserManager',
            component: () => import('@/views/user/user-manager.vue'),
            meta: {
                requiresAuth: true,
            },
        },
    ],
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
