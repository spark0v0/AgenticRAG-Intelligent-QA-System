<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAppearance } from './stores/appearance'

const appearance = useAppearance()
const route = useRoute()
watch(
  [() => appearance.theme, () => route.meta.layout],
  ([theme, layout]) => {
    document.documentElement.dataset.theme = theme
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute(
        'content',
        layout === 'home' ? '#07090d' : theme === 'dark' ? '#18191b' : '#ffffff',
      )
  },
  { immediate: true },
)
watch(
  () => route.meta.title,
  (title) => {
    document.title = title ? `${title} · AgenticRAG` : 'AgenticRAG · 智能问答与检索工作台'
  },
  { immediate: true },
)
</script>
<template>
  <RouterView v-slot="{ Component }">
    <!-- Retain running conversations when visiting the product page. -->
    <KeepAlive include="WorkbenchLayout"><component :is="Component" /></KeepAlive>
  </RouterView>
</template>
