<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWorkbench } from './stores/workbench'
import AppIcon from './components/AppIcon.vue'
import AppSidebar from './components/AppSidebar.vue'

const store = useWorkbench()
const route = useRoute()
const router = useRouter()
const sidebarOpen = ref(false)
watch(
  () => store.theme,
  (value) => (document.documentElement.dataset.theme = value),
  { immediate: true },
)
watch(
  () => route.path,
  () => {
    sidebarOpen.value = false
  },
)
onMounted(() => {
  void store.initialize()
  window.addEventListener('pagehide', store.dispose)
})
onUnmounted(() => {
  window.removeEventListener('pagehide', store.dispose)
  store.dispose()
})
function newChat() {
  store.newChat()
  sidebarOpen.value = false
  void router.push('/chat')
}
async function selectSession(id: string) {
  sidebarOpen.value = false
  await store.loadSession(id)
  await router.push('/chat')
}
</script>
<template>
  <div class="app-shell">
    <button
      v-if="sidebarOpen"
      class="sidebar-overlay"
      aria-label="关闭导航"
      @click="sidebarOpen = false"
    ></button>
    <AppSidebar :open="sidebarOpen" @new-chat="newChat" @select="selectSession" />
    <div class="app-main">
      <header class="topbar">
        <div class="breadcrumb">
          <button class="icon-button mobile-only" aria-label="打开导航" @click="sidebarOpen = true">
            <AppIcon name="menu" /></button
          ><span class="muted breadcrumb-root">工作台</span><span class="breadcrumb-root">/</span
          ><strong>{{ route.meta.title }}</strong>
        </div>
        <div class="header-actions">
          <span class="service-status"
            ><i class="live-dot" :class="{ offline: !store.system || !!store.error }"></i
            >{{ store.error || !store.system ? '服务未连接' : '服务已连接' }}</span
          >
          <button
            class="icon-button"
            :aria-label="store.theme === 'light' ? '切换深色主题' : '切换浅色主题'"
            :title="store.theme === 'light' ? '切换深色主题' : '切换浅色主题'"
            @click="store.toggleTheme()"
          >
            <AppIcon :name="store.theme === 'light' ? 'moon' : 'sun'" :size="18" />
          </button>
        </div>
      </header>
      <div v-if="store.error" class="global-error" role="alert">
        <AppIcon name="alert" :size="17" />{{ store.error
        }}<button @click="store.initialize()">重新连接</button>
      </div>
      <div v-if="store.loading" class="connection-line" role="status">正在连接服务…</div>
      <RouterView />
    </div>
  </div>
</template>
