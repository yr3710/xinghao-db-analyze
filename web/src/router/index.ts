import type { App } from 'vue'
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
    },
    {
      path: '/llm-config',
      name: 'LLMConfig',
      component: () => import('@/views/system/config/llm-config.vue'),
    },
  ],
})


export async function setupRouter(app: App) {
  app.use(router)
  await router.isReady()
}


export default router
