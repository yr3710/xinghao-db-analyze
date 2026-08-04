<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import {useRouter} from 'vue-router'
import {v4 as uuidv4} from 'uuid'
import * as GlobalAPI from '@/api'

import MarkdownPreview from '@/components/MarkdownPreview/index.vue'
import { useBusinessStore } from '@/store/business'
import {
  createHistoryReader,
  parseStoredAnswer,
} from '@/store/business/initChatHistory'

type StreamReader
  = ReadableStreamDefaultReader<string>
    | ReadableStreamDefaultReader<Uint8Array>
interface ConversationItem {
  uuid: string
  chat_id: string
  qa_type: string
  role: 'user' | 'assistant'
  question: string
  reader: StreamReader | null
  isHistory?: boolean
  error?: string
}

interface HistoryItem {
  uuid: string
  question: string
  chat_id: string
  qa_type: string
  datasource_id: number | null
  datasource_name: string | null
}

const router = useRouter()
const businessStore = useBusinessStore()

const inputTextString = ref('')
const generating = ref(false)
const conversationItems = ref<ConversationItem[]>([])
const messagesContainer = ref<HTMLElement | null>(null)
const historyItems = ref<HistoryItem[]>([])
const historyLoading = ref(false)
const historyDetailLoading = ref(false)
const historyError = ref('')
const historySearchText = ref('')
const historyPage = ref(1)
const historyTotalCount = ref(0)
const historyTotalPages = ref(1)

const chatId = ref(uuidv4())

async function scrollToBottom() {
  await nextTick()

  if (messagesContainer.value) {
    messagesContainer.value.scrollTop
        = messagesContainer.value.scrollHeight
  }
}

function addErrorMessage(
    uuid: string,
    message: string,
) {
  conversationItems.value.push({
    uuid,
    chat_id: chatId.value,
    qa_type: 'COMMON_QA',
    role: 'assistant',
    question: '',
    reader: null,
    error: message,
  })
}

async function stopGeneration() {
  if (!generating.value) {
    return
  }

  try {
    const response = await GlobalAPI.stop_chat(
        businessStore.task_id,
        'COMMON_QA',
    )

    if (!response.ok) {
      throw new Error('停止请求失败')
    }

    const result = await response.json()

    if (!result.success && !result.data?.success) {
      console.warn('后端没有找到正在执行的任务')
    }
  } catch (error) {
    console.error('停止生成失败：', error)
  }
}

async function handleCreateStylized() {
  const text = inputTextString.value.trim()

  if (!text || generating.value) {
    return
  }

  const questionUuid = uuidv4()

  conversationItems.value.push({
    uuid: questionUuid,
    chat_id: chatId.value,
    qa_type: 'COMMON_QA',
    role: 'user',
    question: text,
    reader: null,
  })

  inputTextString.value = ''
  generating.value = true

  await scrollToBottom()

  const result
      = await businessStore.createAssistantWriterStylized(
      questionUuid,
      chatId.value,
      chatId.value,
      {
        text,
        file_list: [],
        qa_type: 'COMMON_QA',
        datasource_id: undefined,
        selected_skills: undefined,

        onStreamCompleted: () => {
          generating.value = false
        },
      },
  )

  if (result.needLogin) {
    generating.value = false
    await router.push('/login')
    return
  }

  if (result.permissionDenied) {
    generating.value = false

    addErrorMessage(
        questionUuid,
        result.errorMessage || '没有访问权限',
    )

    await scrollToBottom()
    return
  }

  if (result.error || !result.reader) {
    generating.value = false

    addErrorMessage(
        questionUuid,
        '请求模型失败，请稍后重试',
    )

    await scrollToBottom()
    return
  }

  conversationItems.value.push({
    uuid: questionUuid,
    chat_id: chatId.value,
    qa_type: 'COMMON_QA',
    role: 'assistant',
    question: text,
    reader: result.reader,
  })

  await scrollToBottom()
}

function onFailedReader(index: number) {
  generating.value = false

  const item = conversationItems.value[index]

  if (item) {
    item.error = '读取模型输出失败'
  }
}

function onCompletedReader(index: number) {
  generating.value = false

  if (!conversationItems.value[index]?.isHistory) {
    loadHistory(1)
  }

  scrollToBottom()
}

function newChat() {
  if (generating.value) {
    return
  }

  chatId.value = uuidv4()
  conversationItems.value = []
  inputTextString.value = ''

  businessStore.clearWriterList()
  businessStore.clear_task_id()
  businessStore.clear_record_id()
}

function onInputKeydown(event: KeyboardEvent) {
  if (
      event.key === 'Enter'
      && !event.shiftKey
  ) {
    event.preventDefault()
    handleCreateStylized()
  }
}

async function loadHistory(page = 1) {
  historyLoading.value = true
  historyError.value = ''

  try {
    const response
      = await GlobalAPI.queryUserRecordList(
        page,
        20,
        historySearchText.value.trim(),
      )

    if (response.status === 401) {
      await router.push('/login')
      return
    }

    if (!response.ok) {
      throw new Error(
        `加载历史失败：${response.status}`,
      )
    }

    const result = await response.json()
    const records = result.data?.records

    historyItems.value
      = Array.isArray(records) ? records : []

    historyTotalCount.value
      = result.data?.total_count ?? 0
    historyPage.value
      = result.data?.current_page ?? page
    historyTotalPages.value
      = Math.max(result.data?.total_pages ?? 1, 1)
  } catch (error) {
    console.error('加载历史失败：', error)
    historyError.value = '加载历史失败，请稍后重试'
  } finally {
    historyLoading.value = false
  }
}

async function openHistory(item: HistoryItem) {
  if (generating.value || historyDetailLoading.value) {
    return
  }

  historyDetailLoading.value = true
  historyError.value = ''

  try {
    const records: any[] = []
    let page = 1
    let totalPages = 1

    do {
      const response = await GlobalAPI.queryUserRecords(
        item.chat_id,
        page,
        100,
      )

      if (response.status === 401) {
        await router.push('/login')
        return
      }

      if (!response.ok) {
        throw new Error(
          `加载会话失败：${response.status}`,
        )
      }

      const result = await response.json()
      const pageRecords = result.data?.records

      if (!Array.isArray(pageRecords)) {
        throw new Error('会话记录格式错误')
      }

      records.push(...pageRecords)
      totalPages = Math.max(
        result.data?.total_pages ?? 1,
        1,
      )
      page += 1
    } while (page <= totalPages)

    const restoredItems: ConversationItem[] = []

    for (const record of records) {
      const messageUuid = record.uuid || uuidv4()

      restoredItems.push({
        uuid: messageUuid,
        chat_id: record.chat_id,
        qa_type: record.qa_type,
        role: 'user',
        question: record.question,
        reader: null,
        isHistory: true,
      })

      restoredItems.push({
        uuid: messageUuid,
        chat_id: record.chat_id,
        qa_type: record.qa_type,
        role: 'assistant',
        question: record.question,
        reader: createHistoryReader(
          parseStoredAnswer(record.to2_answer),
        ),
        isHistory: true,
      })
    }

    chatId.value = item.chat_id
    conversationItems.value = restoredItems
    businessStore.clearWriterList()

    await scrollToBottom()
  } catch (error) {
    console.error('加载会话失败：', error)
    historyError.value = '加载会话失败，请稍后重试'
  } finally {
    historyDetailLoading.value = false
  }
}

async function deleteHistory(item: HistoryItem) {
  if (generating.value) {
    return
  }

  const confirmed = window.confirm(
    `确定删除会话“${item.question}”吗？`,
  )

  if (!confirmed) {
    return
  }

  try {
    const response = await GlobalAPI.deleteUserRecords([
      item.chat_id,
    ])

    if (response.status === 401) {
      await router.push('/login')
      return
    }

    if (!response.ok) {
      throw new Error(
        `删除会话失败：${response.status}`,
      )
    }

    if (chatId.value === item.chat_id) {
      newChat()
    }

    const nextPage = (
      historyItems.value.length === 1
      && historyPage.value > 1
    )
      ? historyPage.value - 1
      : historyPage.value

    await loadHistory(nextPage)
  } catch (error) {
    console.error('删除会话失败：', error)
    historyError.value = '删除会话失败，请稍后重试'
  }
}

function searchHistory() {
  loadHistory(1)
}

function clearHistorySearch() {
  historySearchText.value = ''
  loadHistory(1)
}

onMounted(() => {
  loadHistory()
})
</script>

<template>
  <main class="chat-page">
    <aside class="history-panel">
      <button
        type="button"
        class="new-chat-button"
        :disabled="generating"
        @click="newChat"
      >
        新建对话
      </button>

      <form
        class="history-search"
        @submit.prevent="searchHistory"
      >
        <input
          v-model="historySearchText"
          type="search"
          placeholder="搜索历史会话"
        >
        <button type="submit">搜索</button>
        <button
          v-if="historySearchText"
          type="button"
          @click="clearHistorySearch"
        >
          清空
        </button>
      </form>

      <p v-if="historyLoading" class="history-status">
        正在加载历史……
      </p>
      <p v-else-if="historyError" class="history-error">
        {{ historyError }}
      </p>
      <p
        v-else-if="historyItems.length === 0"
        class="history-status"
      >
        暂无历史会话
      </p>

      <div v-else class="history-items">
        <div
          v-for="item in historyItems"
          :key="item.chat_id"
          class="history-row"
          :class="{
            'history-row--active': item.chat_id === chatId,
          }"
        >
          <button
            type="button"
            class="history-open-button"
            :disabled="historyDetailLoading"
            :title="item.question"
            @click="openHistory(item)"
          >
            {{ item.question }}
          </button>
          <button
            type="button"
            class="history-delete-button"
            :disabled="generating"
            aria-label="删除会话"
            @click.stop="deleteHistory(item)"
          >
            删除
          </button>
        </div>
      </div>

      <footer class="history-pagination">
        <button
          type="button"
          :disabled="historyPage <= 1 || historyLoading"
          @click="loadHistory(historyPage - 1)"
        >
          上一页
        </button>
        <span>
          {{ historyPage }} / {{ historyTotalPages }}
          （{{ historyTotalCount }} 个会话）
        </span>
        <button
          type="button"
          :disabled="historyPage >= historyTotalPages || historyLoading"
          @click="loadHistory(historyPage + 1)"
        >
          下一页
        </button>
      </footer>
    </aside>

    <section class="chat-main">
      <header class="chat-header">
        <h1>Aix-DB</h1>
      </header>

      <section
        ref="messagesContainer"
        class="message-list"
      >
        <div
          v-if="conversationItems.length === 0"
          class="empty-message"
        >
          输入一个问题开始对话
        </div>

        <article
          v-for="(item, index) in conversationItems"
          :key="`${item.uuid}-${item.role}`"
          :class="[
            'message-item',
            `message-item--${item.role}`,
          ]"
        >
          <div class="message-name">
            {{ item.role === 'user' ? '你' : 'Aix-DB' }}
          </div>

          <div
            v-if="item.role === 'user'"
            class="user-message"
          >
            {{ item.question }}
          </div>

          <div
            v-else-if="item.error"
            class="error-message"
          >
            {{ item.error }}
          </div>

          <MarkdownPreview
            v-else
            :reader="item.reader"
            :qa-type="item.qa_type"
            :is-init="item.isHistory ?? false"
            model="standard"
            :parent-scoll-bottom-method="scrollToBottom"
            @failed="onFailedReader(index)"
            @completed="onCompletedReader(index)"
            @begin-read="scrollToBottom"
          />
        </article>

        <div
          v-if="generating"
          class="loading-message"
        >
          模型正在生成……
        </div>
      </section>

      <form
        class="input-area"
        @submit.prevent="handleCreateStylized"
      >
        <textarea
          v-model="inputTextString"
          :disabled="generating"
          placeholder="输入问题，Enter 发送，Shift+Enter 换行"
          @keydown="onInputKeydown"
        />

        <button
          v-if="generating"
          type="button"
          class="stop-button"
          @click="stopGeneration"
        >
          停止生成
        </button>

        <button
          v-else
          type="submit"
          :disabled="!inputTextString.trim()"
        >
          发送
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.chat-page {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  width: min(1240px, 100%);
  height: 100vh;
  margin: 0 auto;
  background: white;
}

.history-panel {
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  gap: 12px;
  min-height: 0;
  padding: 16px;
  background: #f7f8fc;
  border-right: 1px solid #eee;
}

.new-chat-button {
  width: 100%;
}

.history-search {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.history-search input {
  width: 100%;
  padding: 8px 10px;
}

.history-status,
.history-error {
  margin: 0;
  color: #888;
  font-size: 14px;
}

.history-error {
  color: #d03050;
}

.history-items {
  min-height: 0;
  overflow-y: auto;
}

.history-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px;
  margin-bottom: 6px;
  border-radius: 8px;
}

.history-row--active {
  background: #e9e7ff;
}

.history-open-button {
  min-width: 0;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: transparent;
  border: 0;
}

.history-delete-button {
  padding-inline: 8px;
  color: #d03050;
  background: transparent;
  border: 0;
}

.history-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #666;
  font-size: 12px;
}

.history-pagination button {
  padding: 5px 8px;
}

.chat-main {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-width: 0;
  min-height: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid #eee;
}

.message-list {
  overflow-y: auto;
  padding: 24px;
}

.empty-message {
  margin-top: 120px;
  color: #999;
  text-align: center;
}

.message-item {
  margin-bottom: 24px;
}

.message-item--user {
  text-align: right;
}

.message-item--assistant {
  text-align: left;
}

.message-name {
  margin-bottom: 6px;
  color: #888;
  font-size: 13px;
}

.user-message {
  display: inline-block;
  max-width: 80%;
  padding: 10px 16px;
  border-radius: 12px;
  background: #f0f3ff;
  text-align: left;
  white-space: pre-wrap;
}

.error-message {
  color: #d03050;
}

.loading-message {
  color: #888;
}

.input-area {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #eee;
}

textarea {
  flex: 1;
  min-height: 72px;
  padding: 10px;
  resize: vertical;
}

button {
  padding: 8px 18px;
}

.stop-button {
  color: white;
  background: #d03050;
}

@media (max-width: 760px) {
  .chat-page {
    grid-template-columns: 1fr;
  }

  .history-panel {
    grid-template-rows: auto auto auto auto;
    max-height: 280px;
    border-right: 0;
    border-bottom: 1px solid #eee;
  }
}
</style>
