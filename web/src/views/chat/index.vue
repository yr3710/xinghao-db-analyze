<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { v4 as uuidv4 } from 'uuid'

import MarkdownPreview from '@/components/MarkdownPreview/index.vue'
import { useBusinessStore } from '@/store/business'

type StreamReader = ReadableStreamDefaultReader<string>

interface ConversationItem {
  uuid: string
  chat_id: string
  qa_type: string
  role: 'user' | 'assistant'
  question: string
  reader: StreamReader | null
  error?: string
}

const router = useRouter()
const businessStore = useBusinessStore()

const inputTextString = ref('')
const generating = ref(false)
const conversationItems = ref<ConversationItem[]>([])
const messagesContainer = ref<HTMLElement | null>(null)

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

function onCompletedReader() {
  generating.value = false
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
</script>

<template>
  <main class="chat-page">
    <header class="chat-header">
      <h1>Aix-DB</h1>

      <button
        type="button"
        :disabled="generating"
        @click="newChat"
      >
        新建对话
      </button>
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
          :is-init="false"
          model="standard"
          :parent-scoll-bottom-method="scrollToBottom"
          @failed="onFailedReader(index)"
          @completed="onCompletedReader"
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
        type="submit"
        :disabled="
          generating
            || !inputTextString.trim()
        "
      >
        {{ generating ? '生成中' : '发送' }}
      </button>
    </form>
  </main>
</template>

<style scoped>
.chat-page {
  display: grid;
  grid-template-rows: auto 1fr auto;
  width: min(960px, 100%);
  height: 100vh;
  margin: 0 auto;
  background: white;
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
</style>