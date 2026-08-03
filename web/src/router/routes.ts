import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Root',
    component: () => import('@/components/Layout/SlotCenterPanel.vue'),
    meta: {
      requiresAuth: true,
    },
    children: [
      {
        path: '',
        name: 'Home',
        component: () => import('@/views/home/index.vue'),
        meta: {
          requiresAuth: true,
        },
      },
      {
        path: 'llm-config',
        name: 'LLMConfig',
        component: () => import('@/views/system/config/llm-config.vue'),
        meta: {
          requiresAuth: true,
        },
      },
      {
        path: 'user-manager',
        name: 'UserManager',
        component: () => import('@/views/user/user-manager.vue'),
        meta: {
          requiresAuth: true,
        },
      },
    ],
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/login.vue'),
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

export default routes