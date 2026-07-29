<script setup lang="ts">
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
      throw new Error(
        `HTTP ${response.status}`,
      )
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
  <main class="page">
    <section class="card">
      <h1>Aix-DB Replica</h1>

      <p v-if="loading">
        正在连接后端……
      </p>

      <p
        v-else-if="errorMessage"
        class="error"
      >
        后端连接失败：{{ errorMessage }}
      </p>

      <template v-else-if="healthData">
        <p>应用：{{ healthData.name }}</p>
        <p>状态：{{ healthData.status }}</p>
      </template>

      <button
        type="button"
        @click="checkBackend"
      >
        重新检查
      </button>
    </section>
  </main>
</template>

<style scoped>
.page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  background: #f5f5f5;
  font-family: Arial, sans-serif;
}

.card {
  width: 360px;
  padding: 32px;
  border-radius: 12px;
  background: white;
  box-shadow: 0 8px 30px rgb(0 0 0 / 8%);
}

.error {
  color: #d03050;
}

button {
  padding: 8px 16px;
  border: 0;
  border-radius: 6px;
  color: white;
  background: #692ee6;
  cursor: pointer;
}
</style>