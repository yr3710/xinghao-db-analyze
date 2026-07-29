import path from 'node:path'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'


export default defineConfig({
  plugins: [
    vue(),
  ],

  server: {
    host: '0.0.0.0',
    port: 2048,
    cors: true,

    proxy: {
      '/sanic': {
        target: 'http://localhost:8088',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/sanic/, ''),
      },
    },
  },

  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
})