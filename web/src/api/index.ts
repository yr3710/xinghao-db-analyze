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