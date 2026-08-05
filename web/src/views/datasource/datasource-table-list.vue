<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import { NButton, NSwitch } from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  fetch_datasource_field_list,
  fetch_datasource_table_list,
  save_datasource_field,
  save_datasource_table,
} from '@/api/datasource'

interface DatasourceTable {
  id: number
  ds_id: number
  table_name: string
  table_comment?: string
  custom_comment?: string
  checked: boolean
}

interface DatasourceField {
  id: number
  ds_id: number
  table_id: number
  field_name: string
  field_type?: string
  field_comment?: string
  custom_comment?: string
  field_index?: number
  checked: boolean
}

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dsId = Number(route.params.dsId)
const dsName = decodeURIComponent(String(route.params.dsName || ''))
const loading = ref(false)
const fieldLoading = ref(false)
const keyword = ref('')
const tableList = ref<DatasourceTable[]>([])
const fieldList = ref<DatasourceField[]>([])
const currentTable = ref<DatasourceTable | null>(null)
const showTableModal = ref(false)
const showFieldModal = ref(false)
const tableComment = ref('')
const fieldComment = ref('')
const currentField = ref<DatasourceField | null>(null)

const filteredTables = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  if (!value)
    return tableList.value
  return tableList.value.filter(table => [
    table.table_name,
    table.table_comment,
    table.custom_comment,
  ].some(text => (text || '').toLowerCase().includes(value)))
})

async function fetchFieldList(table: DatasourceTable) {
  currentTable.value = table
  fieldLoading.value = true
  try {
    const response = await fetch_datasource_field_list(table.id)
    const result = await response.json()
    if (result.code !== 200)
      throw new Error(result.msg || '字段列表加载失败')
    fieldList.value = result.data || []
  }
  catch (error) {
    message.error(error instanceof Error ? error.message : '字段列表加载失败')
  }
  finally {
    fieldLoading.value = false
  }
}

async function fetchTableList() {
  loading.value = true
  try {
    const response = await fetch_datasource_table_list(dsId)
    const result = await response.json()
    if (result.code !== 200)
      throw new Error(result.msg || '表列表加载失败')
    tableList.value = result.data || []
    if (tableList.value.length)
      await fetchFieldList(tableList.value[0])
    else
      fieldList.value = []
  }
  catch (error) {
    message.error(error instanceof Error ? error.message : '表列表加载失败')
  }
  finally {
    loading.value = false
  }
}

function editTable(table: DatasourceTable) {
  currentTable.value = table
  tableComment.value = table.custom_comment || ''
  showTableModal.value = true
}

async function saveTable() {
  if (!currentTable.value)
    return
  try {
    const response = await save_datasource_table({
      id: currentTable.value.id,
      custom_comment: tableComment.value,
      checked: currentTable.value.checked,
    })
    if (!response.ok)
      throw new Error(`HTTP error! status: ${response.status}`)
    const result = await response.json()
    if (result.code !== 200) {
      message.error(result.msg || '表信息保存失败')
      return
    }
    currentTable.value.custom_comment = tableComment.value
    showTableModal.value = false
    message.success('表信息保存成功')
  }
  catch (error) {
    console.error('保存表信息失败:', error)
    message.error('表信息保存失败')
  }
}

async function toggleTable(table: DatasourceTable, checked: boolean) {
  table.checked = checked
  try {
    const response = await save_datasource_table({
      id: table.id,
      custom_comment: table.custom_comment,
      checked,
    })
    if (!response.ok)
      throw new Error(`HTTP error! status: ${response.status}`)
    const result = await response.json()
    if (result.code !== 200)
      message.error(result.msg || '表状态保存失败')
  }
  catch (error) {
    console.error('保存表状态失败:', error)
    message.error('表状态保存失败')
  }
}

function editField(field: DatasourceField) {
  currentField.value = field
  fieldComment.value = field.custom_comment || ''
  showFieldModal.value = true
}

async function saveField() {
  if (!currentField.value)
    return
  try {
    const response = await save_datasource_field({
      id: currentField.value.id,
      custom_comment: fieldComment.value,
      checked: currentField.value.checked,
    })
    if (!response.ok)
      throw new Error(`HTTP error! status: ${response.status}`)
    const result = await response.json()
    if (result.code !== 200) {
      message.error(result.msg || '字段信息保存失败')
      return
    }
    currentField.value.custom_comment = fieldComment.value
    showFieldModal.value = false
    message.success('字段信息保存成功')
  }
  catch (error) {
    console.error('保存字段信息失败:', error)
    message.error('字段信息保存失败')
  }
}

async function toggleField(field: DatasourceField, checked: boolean) {
  field.checked = checked
  try {
    const response = await save_datasource_field({
      id: field.id,
      custom_comment: field.custom_comment,
      checked,
    })
    if (!response.ok)
      throw new Error(`HTTP error! status: ${response.status}`)
    const result = await response.json()
    if (result.code !== 200)
      message.error(result.msg || '字段状态保存失败')
  }
  catch (error) {
    console.error('保存字段状态失败:', error)
    message.error('字段状态保存失败')
  }
}

const fieldColumns: DataTableColumns<DatasourceField> = [
  { title: '字段名', key: 'field_name', minWidth: 150 },
  { title: '类型', key: 'field_type', minWidth: 120 },
  { title: '原始注释', key: 'field_comment', minWidth: 180 },
  { title: '自定义注释', key: 'custom_comment', minWidth: 180 },
  { title: '顺序', key: 'field_index', width: 80 },
  {
    title: '启用', key: 'checked', width: 90,
    render: row => h(NSwitch, {
      value: row.checked,
      'onUpdate:value': value => toggleField(row, value),
    }),
  },
  {
    title: '操作', key: 'actions', width: 90,
    render: row => h(NButton, {
      size: 'small',
      onClick: () => editField(row),
    }, { default: () => '编辑' }),
  },
]

onMounted(fetchTableList)
</script>

<template>
  <section class="schema-page">
    <header class="page-header">
      <div>
        <n-button text @click="router.push('/datasource')">← 返回数据源</n-button>
        <h2>{{ dsName }} · Schema</h2>
      </div>
      <n-button :loading="loading" @click="fetchTableList">刷新</n-button>
    </header>

    <div class="schema-content">
      <aside class="table-panel">
        <n-input v-model:value="keyword" clearable placeholder="搜索表名或注释" />
        <n-spin :show="loading">
          <div class="table-list">
            <button
              v-for="table in filteredTables"
              :key="table.id"
              class="table-item"
              :class="{ active: currentTable?.id === table.id }"
              @click="fetchFieldList(table)"
            >
              <span class="table-name">{{ table.table_name }}</span>
              <span class="table-comment">{{ table.custom_comment || table.table_comment || '暂无注释' }}</span>
            </button>
            <n-empty v-if="!loading && !filteredTables.length" description="暂无已同步表" />
          </div>
        </n-spin>
      </aside>

      <main class="field-panel">
        <template v-if="currentTable">
          <div class="table-header">
            <div>
              <div class="table-title">{{ currentTable.table_name }}</div>
              <div class="table-description">
                原始注释：{{ currentTable.table_comment || '暂无' }}<br>
                自定义注释：{{ currentTable.custom_comment || '暂无' }}
              </div>
            </div>
            <div class="table-actions">
              <n-switch
                :value="currentTable.checked"
                @update:value="value => toggleTable(currentTable!, value)"
              />
              <n-button @click="editTable(currentTable)">编辑表注释</n-button>
            </div>
          </div>
          <n-data-table
            :columns="fieldColumns"
            :data="fieldList"
            :loading="fieldLoading"
            :row-key="row => row.id"
            :scroll-x="1000"
          />
        </template>
        <n-empty v-else description="请选择一张表" />
      </main>
    </div>

    <n-modal
      v-model:show="showTableModal"
      preset="dialog"
      title="编辑表注释"
      positive-text="保存"
      negative-text="取消"
      @positive-click="saveTable"
    >
      <n-input v-model:value="tableComment" type="textarea" :rows="4" />
    </n-modal>

    <n-modal
      v-model:show="showFieldModal"
      preset="dialog"
      title="编辑字段注释"
      positive-text="保存"
      negative-text="取消"
      @positive-click="saveField"
    >
      <n-input v-model:value="fieldComment" type="textarea" :rows="4" />
    </n-modal>
  </section>
</template>

<style scoped>
.schema-page { width: 100%; height: 100%; padding: 24px; overflow: hidden; background: #f7f8fc; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-header h2 { margin: 8px 0 0; font-size: 22px; }
.schema-content { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 16px; height: calc(100% - 76px); }
.table-panel, .field-panel { padding: 16px; overflow: auto; background: #fff; border-radius: 8px; }
.table-list { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.table-item { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; text-align: left; background: #fff; border: 1px solid #eee; border-radius: 6px; cursor: pointer; }
.table-item.active { color: #18a058; background: #f0faf5; border-color: #18a058; }
.table-name { font-weight: 600; }
.table-comment { overflow: hidden; color: #888; text-overflow: ellipsis; white-space: nowrap; }
.table-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.table-title { font-size: 20px; font-weight: 600; }
.table-description { margin-top: 6px; color: #777; line-height: 1.7; }
.table-actions { display: flex; align-items: center; gap: 12px; }
@media (max-width: 800px) {
  .schema-content { grid-template-columns: 1fr; overflow: auto; }
  .table-panel { max-height: 280px; }
}
</style>
