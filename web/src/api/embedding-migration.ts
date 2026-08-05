import { useUserStore } from '@/store/business/userStore'

const BASE_URL = `${location.origin}/sanic/system/embedding-migration`

const getHeaders = () => {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

/**
 * 获取当前 embedding 模型信息
 */
export async function getEmbeddingModelInfo() {
  const url = new URL(`${BASE_URL}/model-info`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: getHeaders(),
  })
  return fetch(req).then((res) => res.json())
}

/**
 * 重新计算 embedding（SSE 流式）
 */
export function recalculateEmbeddings(modules?: string[]) {
  const url = new URL(`${BASE_URL}/recalculate`)
  return fetch(url, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ modules })
  })
}

/**
 * 重新计算 embedding（同步方式）
 */
export async function recalculateEmbeddingsSync(modules?: string[]) {
  const url = new URL(`${BASE_URL}/recalculate-sync`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify({ modules }),
  })
  return fetch(req).then((res) => res.json())
}
