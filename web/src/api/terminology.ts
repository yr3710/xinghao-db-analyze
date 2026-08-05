import { useUserStore } from '@/store/business/userStore'

const BASE_URL = `${location.origin}/sanic/terminology`

const getHeaders = () => {
  const userStore = useUserStore()
  const token = userStore.getUserToken()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  }
}

export async function queryTerminologyList(page: number, size: number, word?: string, dslist?: number[]) {
  const url = new URL(`${BASE_URL}/list`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify({ page, size, word, dslist }),
  })
  return fetch(req)
}

export async function saveTerminology(data: any) {
  const url = new URL(`${BASE_URL}/save`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })
  return fetch(req)
}

export async function deleteTerminology(ids: number[]) {
  const url = new URL(`${BASE_URL}/delete`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify({ ids }),
  })
  return fetch(req)
}

export async function enableTerminology(id: number, enabled: boolean) {
  const enabledInt = enabled ? 1 : 0
  const url = new URL(`${BASE_URL}/${id}/enable/${enabledInt}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: getHeaders(),
  })
  return fetch(req)
}

export async function getTerminologyDetail(id: number) {
  const url = new URL(`${BASE_URL}/${id}`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'get',
    headers: getHeaders(),
  })
  return fetch(req)
}

export async function generateSynonyms(word: string) {
  const url = new URL(`${BASE_URL}/generate_synonyms`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: getHeaders(),
    body: JSON.stringify({ word }),
  })
  return fetch(req)
}
