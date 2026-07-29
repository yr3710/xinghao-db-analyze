<script setup lang="ts">
import {
  NConfigProvider,
  dateZhCN,
  zhCN,
} from 'naive-ui'
import { RouterView } from 'vue-router'

import NaiveProvider from './NaiveProvider.vue'
</script>

<template>
  <NConfigProvider
    :locale="zhCN"
    :date-locale="dateZhCN"
  >
    <NaiveProvider>
      <RouterView />
    </NaiveProvider>
  </NConfigProvider>
</template>