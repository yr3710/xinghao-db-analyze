/**
 * 用户登录
 * @param username
 * @param password
 * @returns
 */
export async function login(username, password) {
  const url = new URL(`${location.origin}/sanic/user/login`)
  const req = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      username,
      password,
    }),
  })
  return fetch(req)
}

export async function createOllama3Stylized(
  text,
  qa_type,
  uuid,
  chat_id,
  file_list,
  datasource_id,
  selected_skills?,
) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()

  const url = new URL(
    `${location.origin}/sanic/dify/get_answer`,
  )

  const controller = new AbortController()

  const timeoutId = setTimeout(() => {
    controller.abort()
  }, 36 * 60 * 1000)

  const request = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      query: text,
      qa_type,
      uuid,
      chat_id,
      file_list,
      datasource_id,
      ...(selected_skills?.length
        ? { selected_skills }
        : {}),
    }),
    signal: controller.signal,
  })

  return fetch(request).finally(() => {
    clearTimeout(timeoutId)
  })
}

export async function stop_chat(
  task_id,
  qa_type,
) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()

  const url = new URL(
    `${location.origin}/sanic/dify/stop_chat`,
  )

  const request = new Request(url, {
    mode: 'cors',
    method: 'post',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      task_id,
      qa_type,
    }),
  })

  return fetch(request)
}