<script setup lang="ts">
import NavBar from '@/components/Navigation/nav-bar.vue'
import NavSidebar from '@/components/Navigation/nav-sidebar.vue'
import NavOctocat from '@/components/Navigation/nav-octocat.vue'
</script>

<template>
  <div class="h-full flex flex-col">
    <NavBar />

    <div class="flex flex-1 overflow-hidden">
      <div class="w-80 h-full">
        <NavSidebar />
      </div>

      <main class="flex-1 p-6">
        <h2>Navigation 组件验证</h2>

        <div class="mt-4 flex items-center">
          Octocat：
          <NavOctocat />
        </div>
      </main>
    </div>
  </div>
</template>