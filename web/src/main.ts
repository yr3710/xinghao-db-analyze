import App from '@/App.vue'
import { setupRouter } from '@/router'
import { setupStore, store } from '@/store'
import { useUserStore } from '@/store/business/userStore'
import 'virtual:uno.css'

const app = createApp(App)

async function setupApp() {
  setupStore(app)

  const userStore = useUserStore(store)
  userStore.init()

  await setupRouter(app)

  app.mount('#app')
}

setupApp()