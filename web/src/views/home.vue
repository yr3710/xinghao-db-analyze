<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/business/userStore'

const router = useRouter()
const userStore = useUserStore()

function handleLogout() {
  userStore.logout()

  setTimeout(() => {
    router.replace('/login')
  }, 100)
}
</script>

<template>
  <div class="p-6">
    <h1>临时首页</h1>

    <n-space class="mt-4">
      <n-button @click="router.push('/llm-config')">
        模型配置
      </n-button>

      <n-button @click="router.push('/user-manager')">
        用户管理
      </n-button>

      <n-button type="error" @click="handleLogout">
        退出登录
      </n-button>
    </n-space>
  </div>
</template>