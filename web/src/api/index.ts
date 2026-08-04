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

function authenticatedPost(
  path: string,
  body: Record<string, unknown>,
) {
  const userStore = useUserStore()
  const token = userStore.getUserToken()

  return fetch(`${location.origin}/sanic${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  })
}

export async function queryUserRecordList(
  page = 1,
  size = 20,
  searchText = '',
) {
  return authenticatedPost('/user/query_user_record_list', {
    page,
    size,
    search_text: searchText,
  })
}

export async function queryUserRecords(
  chatId: string,
  page = 1,
  size = 100,
) {
  return authenticatedPost('/user/query_user_record', {
    page,
    size,
    search_text: '',
    chat_id: chatId,
  })
}

export async function deleteUserRecords(chatIds: string[]) {
  return authenticatedPost('/user/delete_user_record', {
    record_ids: chatIds,
  })
}

export async function get_record_sql(recordId: number) {
  return authenticatedPost('/user/get_record_sql', {
    record_id: recordId,
  })
}
