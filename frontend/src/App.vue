<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWorkbench } from './stores/workbench'
import AppIcon from './components/AppIcon.vue'
import AppSidebar from './components/AppSidebar.vue'

const store = useWorkbench()
const route = useRoute()
const router = useRouter()
const sidebarOpen = ref(false)
const navigationButton = ref<HTMLButtonElement>()
const content = ref<HTMLElement>()
const narrowScreen = window.matchMedia('(max-width: 760px)')
const mobile = ref(narrowScreen.matches)
const navigationModal = computed(() => mobile.value && sidebarOpen.value)
function resizeNavigation() {
  mobile.value = narrowScreen.matches
  if (!mobile.value) sidebarOpen.value = false
}
function focusContent() {
  content.value?.focus({ preventScroll: true })
}
async function openNavigation() {
  sidebarOpen.value = true
  await nextTick()
  document.querySelector<HTMLButtonElement>('#workspace-navigation button')?.focus()
}
async function closeNavigation() {
  sidebarOpen.value = false
  await nextTick()
  navigationButton.value?.focus()
}
async function finishNavigation() {
  if (!navigationModal.value) return
  sidebarOpen.value = false
  await nextTick()
  focusContent()
}
watch(
  () => store.theme,
  (value) => (document.documentElement.dataset.theme = value),
  { immediate: true },
)
watch(
  () => route.path,
  () => {
    void finishNavigation()
  },
)
onMounted(() => {
  void store.initialize()
  window.addEventListener('pagehide', store.dispose)
  narrowScreen.addEventListener('change', resizeNavigation)
})
onUnmounted(() => {
  window.removeEventListener('pagehide', store.dispose)
  narrowScreen.removeEventListener('change', resizeNavigation)
  store.dispose()
})
function newChat() {
  store.newChat()
  void finishNavigation()
  void router.push('/chat')
}
async function selectSession(id: string) {
  void finishNavigation()
  const loading = store.loadSession(id)
  await router.push('/chat')
  await loading
}
</script>
<template>
  <div class="app-shell">
    <a
      v-if="!navigationModal"
      class="skip-link"
      href="#workspace-content"
      @click.prevent="focusContent"
      >跳到主要内容</a
    >
    <header class="topbar" :inert="navigationModal">
      <div class="header-identity">
        <button
          ref="navigationButton"
          class="icon-button mobile-only"
          aria-label="打开导航"
          :aria-expanded="sidebarOpen"
          aria-controls="workspace-navigation"
          @click="openNavigation"
        >
          <AppIcon name="menu" />
        </button>
        <a class="brand" href="/chat" @click.prevent="newChat">
          <span class="brand-mark"><AppIcon name="branch" :size="22" /></span>
          <span>Agentic<span class="brand-light">RAG</span></span>
        </a>
        <div class="breadcrumb">
          <span>知识工作台</span><span>/</span><strong>{{ route.meta.title }}</strong>
        </div>
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
          <AppIcon :name="store.theme === 'light' ? 'moon' : 'sun'" :size="19" />
        </button>
      </div>
    </header>
    <button
      v-if="sidebarOpen"
      class="sidebar-overlay"
      aria-label="关闭导航"
      tabindex="-1"
      @click="closeNavigation"
    ></button>
    <AppSidebar
      :open="sidebarOpen"
      :mobile="mobile"
      @new-chat="newChat"
      @select="selectSession"
      @close="closeNavigation"
      @navigate="finishNavigation"
    />
    <div
      id="workspace-content"
      ref="content"
      class="app-main"
      tabindex="-1"
      :inert="navigationModal"
    >
      <div v-if="store.error" class="global-error" role="alert">
        <AppIcon name="alert" :size="17" />{{ store.error
        }}<button @click="store.initialize()">重新连接</button>
      </div>
      <div v-if="store.loading" class="connection-line" role="status">正在连接服务…</div>
      <RouterView />
    </div>
  </div>
</template>
