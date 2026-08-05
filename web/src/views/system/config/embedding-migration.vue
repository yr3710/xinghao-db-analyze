<template>
  <div class="embedding-migration-container">
    <div class="header">
      <h2 class="title">Embedding 数据迁移</h2>
      <p class="description">
        根据当前 embedding 模型重新计算历史数据的 embedding，实现模型切换后的数据迁移
      </p>
    </div>

    <div class="content">
      <!-- 当前模型信息 -->
      <n-card class="model-info-card">
        <template #header>
          <div class="card-header">
            <span class="i-material-symbols:info-outline text-18"></span>
            <span>当前 Embedding 模型</span>
          </div>
        </template>
        <div v-if="modelInfoLoading" class="loading-info">
          <n-spin size="small" />
          <span>加载中...</span>
        </div>
        <div v-else-if="modelInfo" class="model-info-content">
          <div class="info-item">
            <span class="label">模型类型：</span>
            <n-tag :type="modelInfo.model_type === 'online' ? 'success' : 'info'">
              {{ modelInfo.model_type === 'online' ? '在线模型' : '未配置在线模型' }}
            </n-tag>
          </div>
          <div class="info-item">
            <span class="label">模型名称：</span>
            <span class="value">{{ modelInfo.model_name }}</span>
          </div>
          <div class="info-item">
            <span class="label">向量维度：</span>
            <span class="value">{{ modelInfo.dimension || '未知' }}</span>
          </div>
        </div>
        <div v-else class="error-info">
          <n-alert type="warning">无法获取模型信息</n-alert>
        </div>
      </n-card>

      <!-- 迁移模块选择 -->
      <n-card class="modules-card">
        <template #header>
          <div class="card-header">
            <span class="i-material-symbols:settings-outline text-18"></span>
            <span>选择要迁移的模块</span>
          </div>
        </template>
        <n-checkbox-group v-model:value="selectedModules">
          <div class="module-list">
            <div
              v-for="module in modules"
              :key="module.key"
              class="module-item"
            >
              <n-checkbox :value="module.key" :disabled="migrating">
                <div class="module-content">
                  <div class="module-header">
                    <span :class="[module.icon, 'text-20']"></span>
                    <span class="module-name">{{ module.name }}</span>
                  </div>
                  <p class="module-desc">{{ module.description }}</p>
                </div>
              </n-checkbox>
            </div>
          </div>
        </n-checkbox-group>
      </n-card>

      <!-- 开始迁移按钮 -->
      <div class="action-section">
        <n-button
          type="primary"
          size="large"
          :loading="migrating"
          :disabled="selectedModules.length === 0 || migrating"
          @click="handleStartMigration"
        >
          <template #icon>
            <span class="i-material-symbols:refresh text-18"></span>
          </template>
          {{ migrating ? '迁移中...' : '开始迁移' }}
        </n-button>
      </div>

      <!-- 进度显示 -->
      <n-card v-if="migrating || migrationResults" class="progress-card">
        <template #header>
          <div class="card-header">
            <span class="i-material-symbols:sync text-18"></span>
            <span>迁移进度</span>
          </div>
        </template>

        <!-- 当前模块进度 -->
        <div v-if="currentProgress.module" class="current-progress">
          <div class="progress-header">
            <span class="module-label">{{ getModuleName(currentProgress.module) }}</span>
            <span class="progress-text">
              {{ currentProgress.current }}/{{ currentProgress.total }}
              ({{ currentProgress.percentage }}%)
            </span>
          </div>
          <n-progress
            type="line"
            :percentage="currentProgress.percentage"
            :status="currentProgress.percentage === 100 ? 'success' : 'default'"
            :show-indicator="true"
          />
          <p class="progress-message">{{ currentProgress.message }}</p>
        </div>

        <!-- 各模块结果 -->
        <div v-if="migrationResults" class="results-section">
          <n-divider />
          <div class="results-header">
            <span class="i-material-symbols:check-circle-outline text-18"></span>
            <span>迁移结果</span>
          </div>
          <div class="results-list">
            <div
              v-for="(result, module) in migrationResults"
              :key="module"
              class="result-item"
            >
              <div class="result-header">
                <span
                  :class="[
                    result.success
                      ? 'i-material-symbols:check-circle-rounded'
                      : 'i-material-symbols:error-outline-rounded',
                    'text-18',
                    result.success ? 'text-green-500' : 'text-red-500'
                  ]"
                ></span>
                <span class="result-module">{{ getModuleName(module) }}</span>
              </div>
              <div class="result-content">
                <div class="result-stats">
                  <span>总数：{{ result.total }}</span>
                  <span class="success">成功：{{ result.success_count }}</span>
                  <span class="failed">失败：{{ result.failed_count }}</span>
                </div>
                <p class="result-message">{{ result.message }}</p>
              </div>
            </div>
          </div>
        </div>
      </n-card>

      <!-- 提示信息 -->
      <n-alert type="info" class="tip-alert">
        <template #header>注意事项</template>
        <ul class="tip-list">
          <li>迁移过程可能需要较长时间，请耐心等待，不要关闭页面</li>
          <li>迁移过程中只使用当前配置的在线 embedding 模型，不回退到本地模型</li>
          <li>建议在业务低峰期进行迁移操作</li>
          <li>迁移完成后，相关模块的 embedding 将使用新的模型和维度</li>
        </ul>
      </n-alert>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, h } from 'vue'
import { NCard, NButton, NCheckbox, NCheckboxGroup, NProgress, NAlert, NTag, NSpin, NDivider, useMessage, useDialog } from 'naive-ui'
import { getEmbeddingModelInfo, recalculateEmbeddings } from '@/api/embedding-migration'
import { useUserStore } from '@/store/business/userStore'

const userStore = useUserStore()
const message = useMessage()
const dialog = useDialog()

// 模型信息
const modelInfo = ref<any>(null)
const modelInfoLoading = ref(false)

// 模块配置
const modules = [
  {
    key: 'terminology',
    name: '术语 Embedding',
    icon: 'i-material-symbols:book-outline',
    description: '重新计算所有术语的 embedding，存储在 pgvector 中'
  },
  {
    key: 'training',
    name: '训练数据 Embedding',
    icon: 'i-material-symbols:code',
    description: '重新计算所有训练数据的 embedding，存储在 pgvector 中'
  },
  {
    key: 'table',
    name: '表结构 Embedding',
    icon: 'i-material-symbols:database-outline',
    description: '重新计算所有表结构的 embedding，存储在 FAISS 索引中'
  }
]

const selectedModules = ref<string[]>(['terminology', 'training', 'table'])

// 迁移状态
const migrating = ref(false)
const currentProgress = ref({
  module: '',
  current: 0,
  total: 0,
  percentage: 0,
  message: ''
})
const migrationResults = ref<Record<string, any>>({})

// 获取模块名称
const getModuleName = (key: string) => {
  return modules.find(m => m.key === key)?.name || key
}

// 加载模型信息
const loadModelInfo = async () => {
  modelInfoLoading.value = true
  try {
    const res = await getEmbeddingModelInfo()
    if (res.data) {
      modelInfo.value = res.data
    } else if (res.model_type) {
      modelInfo.value = res
    }
  } catch (e: any) {
    console.error('获取模型信息失败:', e)
    message.error('获取模型信息失败')
  } finally {
    modelInfoLoading.value = false
  }
}

// 开始迁移
const handleStartMigration = async () => {
  if (selectedModules.value.length === 0) {
    message.warning('请至少选择一个要迁移的模块')
    return
  }

  // 确认对话框
  dialog.warning({
    title: '确认迁移',
    content: () => h('div', [
      h('p', { style: 'margin-bottom: 12px;' }, '确定要开始迁移吗？'),
      h('p', { style: 'color: #909399; font-size: 14px;' }, [
        '迁移过程可能需要较长时间，请确保：',
        h('ul', { style: 'margin: 8px 0 0 20px;' }, [
          h('li', '不要关闭此页面'),
          h('li', '网络连接稳定'),
          h('li', '服务器资源充足')
        ])
      ])
    ]),
    positiveText: '开始迁移',
    negativeText: '取消',
    onPositiveClick: async () => {
      await startMigration()
    }
  })
}

// 执行迁移
const startMigration = async () => {
  migrating.value = true
  currentProgress.value = {
    module: '',
    current: 0,
    total: 0,
    percentage: 0,
    message: '准备开始迁移...'
  }
  migrationResults.value = {}

  try {
    const token = userStore.getUserToken()
    const response = await fetch(`${location.origin}/sanic/system/embedding-migration/recalculate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ modules: selectedModules.value })
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()

    if (!reader) {
      throw new Error('无法读取响应流')
    }

    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.trim()) continue
        
        if (line.startsWith('data: ')) {
          try {
            const jsonStr = line.slice(6).trim()
            if (!jsonStr) continue
            
            const data = JSON.parse(jsonStr)
            
            if (data.type === 'start') {
              currentProgress.value.message = data.message
            } else if (data.type === 'progress') {
              currentProgress.value = {
                module: data.module,
                current: data.current,
                total: data.total,
                percentage: data.percentage || (data.total > 0 ? Math.floor((data.current / data.total) * 100) : 0),
                message: data.message
              }
            } else if (data.type === 'complete') {
              migrationResults.value = data.result?.results || {}
              currentProgress.value.percentage = 100
              currentProgress.value.message = '迁移完成！'
              message.success('迁移完成')
            } else if (data.type === 'error') {
              throw new Error(data.message)
            } else if (data.type === 'heartbeat') {
              // 心跳消息，忽略
              continue
            }
          } catch (e: any) {
            console.error('解析 SSE 数据失败:', e, line)
          }
        }
      }
    }

    // 处理剩余的 buffer
    if (buffer.trim()) {
      const lines = buffer.split('\n\n')
      for (const line of lines) {
        if (!line.trim()) continue
        if (line.startsWith('data: ')) {
          try {
            const jsonStr = line.slice(6).trim()
            if (jsonStr) {
              const data = JSON.parse(jsonStr)
              if (data.type === 'complete') {
                migrationResults.value = data.result?.results || {}
              }
            }
          } catch (e) {
            console.error('解析 SSE 数据失败:', e)
          }
        }
      }
    }

  } catch (e: any) {
    console.error('迁移失败:', e)
    message.error(`迁移失败: ${e.message || '未知错误'}`)
    currentProgress.value.message = `迁移失败: ${e.message || '未知错误'}`
  } finally {
    migrating.value = false
  }
}

onMounted(() => {
  loadModelInfo()
})
</script>

<style lang="scss" scoped>
.embedding-migration-container {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
  height: 100%;
  overflow-y: auto;
}

.header {
  margin-bottom: 24px;

  .title {
    font-size: 24px;
    font-weight: 600;
    color: #1f2937;
    margin: 0 0 8px 0;
  }

  .description {
    font-size: 14px;
    color: #6b7280;
    margin: 0;
  }
}

.content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.model-info-card,
.modules-card,
.progress-card {
  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 500;
    color: #1f2937;
  }
}

.model-info-content {
  display: flex;
  flex-direction: column;
  gap: 12px;

  .info-item {
    display: flex;
    align-items: center;
    gap: 8px;

    .label {
      font-weight: 500;
      color: #4b5563;
      min-width: 80px;
    }

    .value {
      color: #1f2937;
    }
  }
}

.loading-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
}

.module-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.module-item {
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  transition: all 0.2s;

  &:hover {
    border-color: #3b82f6;
    background-color: #f9fafb;
  }

  .module-content {
    .module-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 4px;

      .module-name {
        font-weight: 500;
        color: #1f2937;
      }
    }

    .module-desc {
      margin: 4px 0 0 28px;
      font-size: 13px;
      color: #6b7280;
    }
  }
}

.action-section {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

.current-progress {
  margin-bottom: 20px;

  .progress-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;

    .module-label {
      font-weight: 500;
      color: #1f2937;
    }

    .progress-text {
      font-size: 14px;
      color: #6b7280;
    }
  }

  .progress-message {
    margin-top: 8px;
    font-size: 13px;
    color: #6b7280;
  }
}

.results-section {
  .results-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 500;
    color: #1f2937;
    margin-bottom: 16px;
  }

  .results-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .result-item {
    padding: 16px;
    background-color: #f9fafb;
    border-radius: 8px;

    .result-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;

      .result-module {
        font-weight: 500;
        color: #1f2937;
      }
    }

    .result-content {
      margin-left: 28px;

      .result-stats {
        display: flex;
        gap: 16px;
        margin-bottom: 4px;
        font-size: 14px;

        .success {
          color: #18a058;
        }

        .failed {
          color: #d03050;
        }
      }

      .result-message {
        margin-top: 4px;
        font-size: 13px;
        color: #6b7280;
      }
    }
  }
}

.tip-alert {
  margin-top: 20px;

  .tip-list {
    margin: 8px 0 0 20px;
    padding: 0;
    color: #6b7280;
    font-size: 14px;
    line-height: 1.8;

    li {
      margin-bottom: 4px;
    }
  }
}
</style>
