<script setup lang="ts">
import {
  NAlert,
  NButton,
  NCard,
  NSpace,
  NSpin,
} from 'naive-ui'
import { onMounted, ref } from 'vue'


interface HealthData {
  name: string
  status: string
}


const loading = ref(false)
const errorMessage = ref('')
const healthData = ref<HealthData | null>(null)


async function checkBackend() {
  loading.value = true
  errorMessage.value = ''

  try {
    const response = await fetch(
      '/sanic/system/health',
    )

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const result = await response.json()
    healthData.value = result.data
  }
  catch (error) {
    errorMessage.value = (
      error instanceof Error
        ? error.message
        : '未知错误'
    )
  }
  finally {
    loading.value = false
  }
}


onMounted(checkBackend)
</script>

<template>
  <main class="min-h-screen bg-[#f5f5f5] grid place-items-center">
    <NCard
      title="Aix-DB Replica"
      class="card"
    >
      <NSpin :show="loading">
        <NSpace vertical>
          <NAlert
            v-if="errorMessage"
            type="error"
          >
            后端连接失败：{{ errorMessage }}
          </NAlert>

          <NAlert
            v-else-if="healthData"
            type="success"
          >
            {{ healthData.name }}：
            {{ healthData.status }}
          </NAlert>

          <NButton
            type="primary"
            @click="checkBackend"
          >
            检查后端
          </NButton>
        </NSpace>
      </NSpin>
    </NCard>
  </main>
</template>

<style scoped>
.page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  background: #f5f5f5;
}

.card {
  width: 420px;
}
</style>