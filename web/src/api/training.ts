import { useUserStore } from '@/store/business/userStore'

const BASE_URL = `${location.origin}/sanic/system/data-training`

function getHeaders() {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

export const trainingApi = {
  getList(pageNum: number, pageSize: number, params: any) {
    const url = new URL(`${BASE_URL}/page/${pageNum}/${pageSize}`)
    if (params) {
      Object.keys(params).forEach((key) => {
        const value = params[key]
        if (value !== undefined && value !== null && value !== '')
          url.searchParams.append(key, value)
      })
    }
    return fetch(new Request(url, {
      mode: 'cors',
      method: 'get',
      headers: getHeaders(),
    }))
  },

  updateEmbedded(data: any) {
    const url = new URL(`${BASE_URL}/`)
    return fetch(new Request(url, {
      mode: 'cors',
      method: 'put',
      headers: getHeaders(),
      body: JSON.stringify(data),
    }))
  },

  deleteEmbedded(params: any) {
    const url = new URL(`${BASE_URL}/`)
    return fetch(new Request(url, {
      mode: 'cors',
      method: 'delete',
      headers: getHeaders(),
      body: JSON.stringify(params),
    }))
  },

  enable(id: number, enabled: boolean) {
    const url = new URL(`${BASE_URL}/${id}/enable/${enabled}`)
    return fetch(new Request(url, {
      mode: 'cors',
      method: 'get',
      headers: getHeaders(),
    }))
  },
}
