<script setup lang="ts">
import { ref } from 'vue'
import SideBar from '@/components/Navigation/SideBar.vue'

const mode = ref<'sidebar' | 'avatar'>('sidebar')
</script>

<template>
  <div class="h-full flex">
    <SideBar
      :mode="mode"
      class="shrink-0"
    />

    <main class="flex-1 p-6">
      <h2>SideBar 功能验证</h2>

      <n-radio-group v-model:value="mode" class="mt-4">
        <n-radio-button value="sidebar">
          完整侧边栏
        </n-radio-button>

        <n-radio-button value="avatar">
          头像菜单
        </n-radio-button>
      </n-radio-group>
    </main>
  </div>
</template>