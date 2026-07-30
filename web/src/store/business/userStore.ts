import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') ?? '')

  function getUserToken() {
    return token.value
  }

  function setUserToken(value: string) {
    token.value = value
    localStorage.setItem('token', value)
  }

  function clearUserToken() {
    token.value = ''
    localStorage.removeItem('token')
  }

  return {
    token,
    getUserToken,
    setUserToken,
    clearUserToken,
  }
})