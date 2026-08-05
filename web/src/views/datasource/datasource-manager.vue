<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import { NButton, NSpace, NTag } from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import {
  delete_datasource,
  fetch_datasource_detail,
  fetch_datasource_list,
} from '@/api/datasource'
import DatasourceAuthModal from '@/components/datasource/datasource-auth-modal.vue'
import DatasourceForm from '@/components/datasource/datasource-form.vue'
import { useUserStore } from '@/store/business/userStore'

interface DatasourceItem {
  id: number
  name: string
  description?: string
  type: 'pg'
  type_name?: string
  status?: string
  num?: string
  host?: string
  database?: string
  create_time?: string
}

interface DatasourceDetail extends DatasourceItem {
  configuration: string
}

const userStore = useUserStore()
const message = useMessage()
const dialog = useDialog()
const loading = ref(false)
const keywords = ref('')
const datasourceList = ref<DatasourceItem[]>([])
const currentDatasource = ref<DatasourceDetail | null>(null)
const authDatasource = ref<DatasourceItem | null>(null)
const showForm = ref(false)
const showAuthModal = ref(false)

const isAdmin = computed(() => userStore.isAdmin)
const filteredList = computed(() => {
  const keyword = keywords.value.trim().toLowerCase()
  if (!keyword)
    return datasourceList.value
  return datasourceList.value.filter(item => [
    item.name,
    item.description,
    item.host,
    item.database,
  ].some(value => (value ?? '').toLowerCase().includes(keyword)))
})

async function loadDatasourceList() {
  loading.value = true
  try {
    const response = await fetch_datasource_list()
    const result = await response.json()
    if (result.code !== 200)
      throw new Error(result.msg || '数据源加载失败')
    datasourceList.value = result.data ?? []
  }
  catch (error) {
    message.error(error instanceof Error ? error.message : '数据源加载失败')
  }
  finally { loading.value = false }
}

function addDatasource() {
  currentDatasource.value = null
  showForm.value = true
}

async function editDatasource(item: DatasourceItem) {
  loading.value = true
  try {
    const response = await fetch_datasource_detail(item.id)
    const result = await response.json()
    if (result.code !== 200)
      throw new Error(result.msg || '详情加载失败')
    currentDatasource.value = result.data
    showForm.value = true
  }
  catch (error) {
    message.error(error instanceof Error ? error.message : '详情加载失败')
  }
  finally { loading.value = false }
}

function deleteDatasource(item: DatasourceItem) {
  dialog.warning({
    title: '删除数据源',
    content: `确定删除“${item.name}”吗？关联授权、表和字段记录也会删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const response = await delete_datasource(item.id)
        const result = await response.json()
        if (result.code !== 200)
          throw new Error(result.msg || '删除失败')
        message.success('删除成功')
        await loadDatasourceList()
      }
      catch (error) {
        message.error(error instanceof Error ? error.message : '删除失败')
      }
    },
  })
}

function authorizeDatasource(item: DatasourceItem) {
  authDatasource.value = item
  showAuthModal.value = true
}

const columns = computed<DataTableColumns<DatasourceItem>>(() => {
  const base: DataTableColumns<DatasourceItem> = [
    { title: '名称', key: 'name', minWidth: 150 },
    { title: '类型', key: 'type_name', width: 130 },
    { title: '主机', key: 'host', minWidth: 140 },
    { title: '数据库', key: 'database', minWidth: 130 },
    {
      title: '状态', key: 'status', width: 100,
      render: row => h(NTag, {
        type: row.status === 'Success' ? 'success' : 'error',
        bordered: false,
      }, { default: () => row.status ?? 'Unknown' }),
    },
    { title: '创建时间', key: 'create_time', minWidth: 170 },
  ]
  if (!isAdmin.value)
    return base
  base.push({
    title: '操作', key: 'actions', width: 230, fixed: 'right',
    render: row => h(NSpace, {}, {
      default: () => [
        h(NButton, { size: 'small', onClick: () => editDatasource(row) }, { default: () => '编辑' }),
        h(NButton, { size: 'small', type: 'info', secondary: true, onClick: () => authorizeDatasource(row) }, { default: () => '授权' }),
        h(NButton, { size: 'small', type: 'error', secondary: true, onClick: () => deleteDatasource(row) }, { default: () => '删除' }),
      ],
    }),
  })
  return base
})

onMounted(loadDatasourceList)
</script>

<template>
  <section class="datasource-manager">
    <header class="page-header">
      <div>
        <h2>数据源管理</h2>
        <p>{{ isAdmin ? '管理数据库连接及用户授权' : '查看已授权的数据源' }}</p>
      </div>
      <div class="header-actions">
        <n-input v-model:value="keywords" clearable placeholder="搜索名称、主机或数据库" />
        <n-button type="primary" :loading="loading" @click="loadDatasourceList">刷新</n-button>
        <n-button v-if="isAdmin" type="primary" @click="addDatasource">新增数据源</n-button>
      </div>
    </header>

    <n-alert v-if="!isAdmin" type="info" class="mb-16">
      普通用户只会看到管理员授权且已启用的数据源。
    </n-alert>

    <n-data-table
      :columns="columns"
      :data="filteredList"
      :loading="loading"
      :row-key="row => row.id"
      :scroll-x="1050"
    />

    <DatasourceForm
      v-model:show="showForm"
      :datasource="currentDatasource"
      @success="loadDatasourceList"
    />
    <DatasourceAuthModal
      v-if="authDatasource"
      v-model:show="showAuthModal"
      :datasource-id="authDatasource.id"
      :datasource-name="authDatasource.name"
      @success="loadDatasourceList"
    />
  </section>
</template>

<style scoped>
.datasource-manager { width: 100%; height: 100%; padding: 24px; overflow: auto; background: #f7f8fc; }
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 20px; }
.page-header h2 { margin: 0 0 6px; font-size: 24px; }
.page-header p { margin: 0; color: #888; }
.header-actions { display: flex; align-items: center; gap: 10px; min-width: min(560px, 55vw); }
@media (max-width: 760px) {
  .page-header { align-items: stretch; flex-direction: column; }
  .header-actions { flex-wrap: wrap; min-width: 0; }
}
</style>
