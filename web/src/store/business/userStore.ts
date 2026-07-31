// src/store/userStore.ts
import { defineStore } from 'pinia'

function parseJwt(token: string) {
  try {
    const base64Url = token.split('.')[1]
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(window.atob(base64).split('').map((c) => {
      return `%${(`00${c.charCodeAt(0).toString(16)}`).slice(-2)}`
    }).join(''))

    return JSON.parse(jsonPayload)
  } catch (e) {
    console.error('Failed to parse JWT', e)
    return {}
  }
}

export const useUserStore = defineStore('user', {
  state: () => ({
    user: null as null | { token: string },
    role: 'user', // default role
  }),
  actions: {
    login(user: { token: string }) {
      this.user = user
      // Parse token to get role
      const payload = parseJwt(user.token)
      this.role = payload.role || 'user'

      // Store token
      sessionStorage.setItem('user', JSON.stringify(user))
    },
    logout() {
      this.user = null
      this.role = 'user'
      sessionStorage.removeItem('user')
    },
    init() {
      const storedUser = sessionStorage.getItem('user')
      if (storedUser) {
        this.user = JSON.parse(storedUser)
        if (this.user?.token) {
          const payload = parseJwt(this.user.token)
          this.role = payload.role || 'user'
        }
      }
    },
    getUserToken() {
      if (!this.user) {
        const storedUser = sessionStorage.getItem('user')
        if (storedUser) {
          this.user = JSON.parse(storedUser)
        }
      }
      return this.user?.token
    },
  },
  getters: {
    isLoggedIn: (state) => !!state.user,
    isAdmin: (state) => state.role === 'admin',
  },
})
