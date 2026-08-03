<script setup lang="ts">
import SlotFrame from '@/components/Layout/SlotFrame.vue'
import SlotArea from '@/components/Layout/SlotArea.vue'
import SidebarPage from '@/components/Layout/sidebar-page.vue'
import NavBar from '@/components/Navigation/nav-bar.vue'
import NavFooter from '@/components/Navigation/nav-footer.vue'
</script>

<template>
  <SlotFrame>
    <template #top>
      <NavBar class="w-full" />
    </template>

    <template #center>
      <SlotArea>
        <template #left>
          <SidebarPage />
        </template>

        <template #right>
          <div class="p-6">
            <h2>Layout 功能验证</h2>
            <p>右侧内容区域</p>
          </div>
        </template>
      </SlotArea>
    </template>

    <template #bottom>
      <NavFooter />
    </template>
  </SlotFrame>
</template>