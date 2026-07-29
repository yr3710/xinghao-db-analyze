import path from 'node:path'

import vue from '@vitejs/plugin-vue'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'
import Components from 'unplugin-vue-components/vite'
import AutoImport from 'unplugin-auto-import/vite'
import IconsResolver from 'unplugin-icons/resolver'
import Icons from 'unplugin-icons/vite'
import UnoCSS from 'unocss/vite'
import { defineConfig } from 'vite'


export default defineConfig({
  plugins: [
    UnoCSS(),

    vue(),

    AutoImport({
      include: [
        /\.[tj]sx?$/,
        /\.vue\??/,
      ],

      imports: [
        'vue',
        'vue-router',
        '@vueuse/core',
        {
          'naive-ui': [
            'useDialog',
            'useMessage',
            'useNotification',
            'useLoadingBar',
          ],
        },
      ],

      resolvers: [
        NaiveUiResolver(),
      ],

      dts: './auto-imports.d.ts',
      vueTemplate: true,
    }),

    Components({
      resolvers: [
        IconsResolver({
          prefix: 'auto-icon',
        }),
        NaiveUiResolver(),
      ],
    }),

    Icons({
      autoInstall: true,
      compiler: 'vue3',
      scale: 1.2,
    }),
  ],

  server: {
    host: '0.0.0.0',
    port: 2048,
    cors: true,

    proxy: {
      '/sanic': {
        target: 'http://localhost:8088',
        changeOrigin: true,
        rewrite: path => path.replace(
          /^\/sanic/,
          '',
        ),
      },
    },
  },

  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
})