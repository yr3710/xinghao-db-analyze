import type {RouteRecordRaw} from 'vue-router'

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
                path: 'chat',
                name: 'Chat',
                component: () => import('@/views/chat/index.vue'),
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
                    title: '用户管理',
                },
            },
            {
                path: 'datasource',
                name: 'DatasourceManager',
                component: () => import('@/views/datasource/datasource-manager.vue'),
                meta: {
                    requiresAuth: true,
                    title: '数据源管理',
                },
            },
            {
                path: 'sidebar-preview',
                name: 'SidebarPreview',
                component: () => import('@/views/dev/sidebar-preview.vue'),
                meta: {
                    requiresAuth: true,
                },
            },
            {
                path: 'navigation-preview',
                name: 'NavigationPreview',
                component: () => import('@/views/dev/navigation-preview.vue'),
                meta: {
                    requiresAuth: true,
                    title: '导航组件验证',
                },
            },
            {
                path: 'navigation-preview/:previewId',
                name: 'NavigationPreviewDynamic',
                component: () => import('@/views/dev/navigation-preview.vue'),
                meta: {
                    requiresAuth: true,
                    title: '动态路由验证',
                },
            },
            {
                path: 'layout-preview',
                name: 'LayoutPreview',
                component: () => import('@/views/dev/layout-preview.vue'),
                meta: {
                    requiresAuth: true,
                    title: '布局验证',
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