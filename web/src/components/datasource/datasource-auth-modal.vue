<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { authorize_datasource, get_authorized_users } from '@/api/datasource'
import { queryUserList } from '@/api/user'

interface UserItem {
  id: number
  userName: string
  mobile?: string
  role?: string
}

const props = defineProps<{
  show: boolean
  datasourceId: number
  datasourceName: string
}>()
const emit = defineEmits<{
  'update:show': [value: boolean]
  'success': []
}>()

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const searchKeyword = ref('')
const userList = ref<UserItem[]>([])
const selectedUserIds = ref<number[]>([])

const modalShow = computed({
  get: () => props.show,
  set: value => emit('update:show', value),
})
const filteredUsers = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  return userList.value.filter((user) => {
    if (user.role === 'admin')
      return false
    if (!keyword)
      return true
    return user.userName.toLowerCase().includes(keyword)
      || (user.mobile ?? '').includes(keyword)
  })
})

async function loadAuthorization() {
  if (!props.datasourceId)
    return
  loading.value = true
  try {
    const [usersResponse, authorizedResponse] = await Promise.all([
      queryUserList(1, 1000),
      get_authorized_users(props.datasourceId),
    ])
    const users = await usersResponse.json()
    const authorized = await authorizedResponse.json()
    if (users.code !== 200 || authorized.code !== 200)
      throw new Error(users.msg || authorized.msg || '授权信息加载失败')
    userList.value = users.data?.records ?? []
    selectedUserIds.value = authorized.data ?? []
  }
  catch (error) {
    message.error(error instanceof Error ? error.message : '授权信息加载失败')
  }
  finally { loading.value = false }
}

async function saveAuthorization() {
  saving.value = true
  try {
    const response = await authorize_datasource(
      props.datasourceId,
      selectedUserIds.value,
    )
    const result = await response.json()
    if (result.code !== 200)
      throw new Error(result.msg || '授权保存失败')
    message.success(
      selectedUserIds.value.length ? '授权保存成功' : '已清空授权',
    )
    emit('success')
    emit('update:show', false)
  }
  catch (error) {
    message.error(error instanceof Error ? error.message : '授权保存失败')
  }
  finally { saving.value = false }
}

watch(() => props.show, (show) => {
  if (show) {
    searchKeyword.value = ''
    selectedUserIds.value = []
    loadAuthorization()
  }
})
</script>

<template>
  <n-modal
    v-model:show="modalShow"
    preset="card"
    :title="`授权用户：${datasourceName}`"
    class="datasource-auth-modal"
  >
    <n-input
      v-model:value="searchKeyword"
      clearable
      placeholder="搜索用户名或手机号"
      class="mb-16"
    />
    <n-spin :show="loading">
      <n-checkbox-group v-model:value="selectedUserIds">
        <div v-if="filteredUsers.length" class="user-list">
          <label v-for="user in filteredUsers" :key="user.id" class="user-row">
            <n-checkbox :value="user.id" />
            <span class="user-name">{{ user.userName }}</span>
            <span class="user-mobile">{{ user.mobile || '未绑定手机号' }}</span>
          </label>
        </div>
        <n-empty v-else description="没有可授权的普通用户" />
      </n-checkbox-group>
    </n-spin>
    <template #footer>
      <div class="flex items-center justify-between">
        <span>已选择 {{ selectedUserIds.length }} 人</span>
        <div class="flex gap-10">
          <n-button @click="modalShow = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="saveAuthorization">
            {{ selectedUserIds.length ? '保存授权' : '清空授权' }}
          </n-button>
        </div>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.datasource-auth-modal { width: min(620px, calc(100vw - 32px)); }
.user-list { max-height: 420px; overflow-y: auto; }
.user-row {
  display: grid; grid-template-columns: auto minmax(120px, 1fr) minmax(140px, 1fr);
  align-items: center; gap: 12px; padding: 12px;
  border-bottom: 1px solid #eee; cursor: pointer;
}
.user-name { font-weight: 600; }
.user-mobile { color: #888; }
</style>
