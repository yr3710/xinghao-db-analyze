<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import { computed, reactive, ref, watch } from 'vue'
import {
  add_datasource,
  check_datasource_connection,
  update_datasource,
} from '@/api/datasource'

interface DatasourceConfiguration {
  host: string
  port: number
  username: string
  password: string
  database: string
  dbSchema: string
  extraJdbc: string
  timeout: number
  mode: string
}

interface DatasourceDetail {
  id: number
  name: string
  description?: string
  type: string
  type_name?: string
  configuration: string
}

interface SaveDatasourcePayload {
  name: string
  description?: string
  type: string
  type_name: string
  configuration: string
}

interface Props {
  show: boolean
  datasource?: DatasourceDetail | null
}

const props = withDefaults(defineProps<Props>(), { datasource: null })
const emit = defineEmits<{
  'update:show': [value: boolean]
  'success': []
}>()

const message = useMessage()
const formRef = ref<FormInst | null>(null)
const saving = ref(false)
const testing = ref(false)
const connectionVerified = ref(false)

// { label: 'AWS Redshift', value: 'redshift' },
// { label: 'Elasticsearch', value: 'es' },
// { label: 'Kingbase', value: 'kingbase' },
const datasourceTypes = [
  { label: 'MySQL', value: 'mysql' },
  { label: 'PostgreSQL', value: 'pg' },
  { label: 'Oracle', value: 'oracle' },
  { label: 'SQL Server', value: 'sqlServer' },
  { label: 'ClickHouse', value: 'ck' },
  { label: '达梦', value: 'dm' },
  { label: 'Apache Doris', value: 'doris' },
  { label: 'StarRocks', value: 'starrocks' },
]

const needSchemaTypes = ['sqlServer', 'pg', 'oracle', 'dm', 'redshift', 'kingbase']
const defaultPorts: Record<string, number> = {
  mysql: 3306,
  pg: 5432,
  oracle: 1521,
  sqlServer: 1433,
  ck: 8123,
  dm: 5236,
  doris: 9030,
  redshift: 5439,
  es: 9200,
  kingbase: 54321,
  starrocks: 9030,
}

const formData = reactive({
  name: '', description: '', type: 'mysql',
  host: '', port: 3306, username: '', password: '',
  database: '', dbSchema: '', extraJdbc: '', timeout: 30,
  mode: 'service_name',
})

const rules: FormRules = {
  name: { required: true, message: '请输入数据源名称', trigger: 'blur' },
  type: { required: true, message: '请选择数据源类型', trigger: 'change' },
  host: { required: true, message: '请输入主机地址', trigger: 'blur' },
  port: { required: true, type: 'number', message: '请输入端口', trigger: 'blur' },
  database: { required: true, message: '请输入数据库名', trigger: 'blur' },
  dbSchema: { required: true, message: '请输入 Schema', trigger: 'blur' },
}

const modalTitle = computed(() => props.datasource
  ? '编辑数据源'
  : '新增数据源')
const showSchema = computed(() => needSchemaTypes.includes(formData.type))
const showOracleMode = computed(() => formData.type === 'oracle')
const modalShow = computed({
  get: () => props.show,
  set: value => emit('update:show', value),
})

function resetForm() {
  Object.assign(formData, {
    name: '', description: '', type: 'mysql', host: '', port: 3306,
    username: '', password: '', database: '', dbSchema: '',
    extraJdbc: '', timeout: 30, mode: 'service_name',
  })
  connectionVerified.value = false
  if (!props.datasource)
    return

  formData.name = props.datasource.name
  formData.description = props.datasource.description ?? ''
  formData.type = props.datasource.type || 'mysql'
  try {
    const config = JSON.parse(props.datasource.configuration) as Partial<DatasourceConfiguration>
    formData.host = config.host ?? ''
    formData.port = Number(config.port ?? defaultPorts[formData.type] ?? 3306)
    formData.username = config.username ?? ''
    formData.password = config.password ?? ''
    formData.database = config.database ?? ''
    formData.dbSchema = config.dbSchema ?? ''
    formData.extraJdbc = config.extraJdbc ?? ''
    formData.timeout = Number(config.timeout ?? 30)
    formData.mode = config.mode ?? 'service_name'
  }
  catch {
    message.error('数据源配置格式错误')
  }
}

function buildConfiguration(): DatasourceConfiguration {
  return {
    host: formData.host.trim(), port: Number(formData.port),
    username: formData.username.trim(), password: formData.password,
    database: formData.database.trim(),
    dbSchema: formData.dbSchema.trim() || formData.database.trim(),
    extraJdbc: formData.extraJdbc.trim(), timeout: Number(formData.timeout),
    mode: formData.mode,
  }
}

function buildPayload(): SaveDatasourcePayload {
  return {
    name: formData.name.trim(), description: formData.description.trim(),
    type: formData.type,
    type_name: datasourceTypes.find(item => item.value === formData.type)?.label || formData.type,
    configuration: JSON.stringify(buildConfiguration()),
  }
}

async function testConnection() {
  try { await formRef.value?.validate() }
  catch { return }
  testing.value = true
  try {
    const response = await check_datasource_connection({
      id: props.datasource?.id,
      type: formData.type,
      configuration: JSON.stringify(buildConfiguration()),
    })
    const result = await response.json()
    connectionVerified.value = result.code === 200 && result.data?.connected
    connectionVerified.value
      ? message.success('连接成功')
      : message.error(result.data?.error_message || result.msg || '连接失败')
  }
  catch (error) {
    connectionVerified.value = false
    message.error(error instanceof Error ? error.message : '连接测试失败')
  }
  finally { testing.value = false }
}

async function saveDatasource() {
  try { await formRef.value?.validate() }
  catch { return }
  if (!connectionVerified.value) {
    message.warning('请先测试并确认连接成功')
    return
  }
  saving.value = true
  try {
    const payload = buildPayload()
    const response = props.datasource
      ? await update_datasource({ ...payload, id: props.datasource.id })
      : await add_datasource(payload)
    const result = await response.json()
    if (result.code !== 200)
      throw new Error(result.msg || '保存失败')
    message.success('数据源保存成功')
    emit('success')
    emit('update:show', false)
  }
  catch (error) {
    message.error(error instanceof Error ? error.message : '保存失败')
  }
  finally { saving.value = false }
}

watch(() => props.show, show => show && resetForm())
watch(() => formData.type, (type, previousType) => {
  if (type !== previousType)
    formData.port = defaultPorts[type] ?? 3306
})
watch(formData, () => { connectionVerified.value = false }, { deep: true })
</script>

<template>
  <n-modal
    v-model:show="modalShow"
    preset="card"
    :title="modalTitle"
    class="datasource-form-modal"
    :mask-closable="false"
  >
    <n-form ref="formRef" :model="formData" :rules="rules" label-placement="top">
      <n-grid :cols="2" :x-gap="16">
        <n-form-item-gi label="数据源名称" path="name">
          <n-input v-model:value="formData.name" placeholder="例如：业务分析库" />
        </n-form-item-gi>
        <n-form-item-gi label="数据库类型" path="type">
          <n-select v-model:value="formData.type" :options="datasourceTypes" />
        </n-form-item-gi>
      </n-grid>
      <n-form-item label="描述">
        <n-input v-model:value="formData.description" type="textarea" placeholder="数据源用途" />
      </n-form-item>
      <n-grid :cols="2" :x-gap="16">
        <n-form-item-gi label="主机" path="host"><n-input v-model:value="formData.host" placeholder="127.0.0.1" /></n-form-item-gi>
        <n-form-item-gi label="端口" path="port"><n-input-number v-model:value="formData.port" :min="1" :max="65535" class="w-full" /></n-form-item-gi>
        <n-form-item-gi label="用户名" path="username"><n-input v-model:value="formData.username" autocomplete="off" /></n-form-item-gi>
        <n-form-item-gi label="密码" path="password"><n-input v-model:value="formData.password" type="password" show-password-on="click" autocomplete="new-password" /></n-form-item-gi>
        <n-form-item-gi label="数据库" path="database"><n-input v-model:value="formData.database" /></n-form-item-gi>
        <n-form-item-gi v-if="showSchema" label="Schema" path="dbSchema"><n-input v-model:value="formData.dbSchema" placeholder="public" /></n-form-item-gi>
        <n-form-item-gi v-if="showOracleMode" label="连接模式" path="mode">
          <n-select
            v-model:value="formData.mode"
            :options="[
              { label: 'Service Name', value: 'service_name' },
              { label: 'SID', value: 'sid' },
            ]"
          />
        </n-form-item-gi>
        <n-form-item-gi label="超时时间（秒）"><n-input-number v-model:value="formData.timeout" :min="1" :max="300" class="w-full" /></n-form-item-gi>
        <n-form-item-gi label="额外连接参数"><n-input v-model:value="formData.extraJdbc" placeholder="例如：sslmode=disable" /></n-form-item-gi>
      </n-grid>
    </n-form>
    <template #footer>
      <div class="flex justify-end gap-10">
        <n-button @click="modalShow = false">取消</n-button>
        <n-button :loading="testing" @click="testConnection">测试连接</n-button>
        <n-button type="primary" :loading="saving" @click="saveDatasource">保存</n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.datasource-form-modal { width: min(760px, calc(100vw - 32px)); }
</style>
