<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { useWorkbench } from '../stores/workbench'
import AppIcon from './AppIcon.vue'
const props = defineProps<{ open: boolean; mobile: boolean }>()
const emit = defineEmits<{ newChat: []; select: [id: string]; close: []; navigate: [] }>()
const store = useWorkbench()
const search = ref('')
const searchInput = ref<HTMLInputElement>()
const navigation = ref<HTMLElement>()
const refreshing = ref(false)
const refreshError = ref('')
let refreshController: AbortController | undefined
onBeforeUnmount(() => refreshController?.abort())
async function refreshHistory() {
  if (refreshing.value) return
  const controller = new AbortController()
  refreshController = controller
  refreshing.value = true
  refreshError.value = ''
  try {
    await store.refreshSessions(controller.signal)
  } catch (cause) {
    if (!controller.signal.aborted)
      refreshError.value = cause instanceof Error ? cause.message : '记录刷新失败，请重试'
  } finally {
    if (!controller.signal.aborted) refreshing.value = false
  }
}
async function clearSearch() {
  search.value = ''
  await nextTick()
  searchInput.value?.focus()
}
function navigate(event: MouseEvent) {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  if (event.target instanceof Element && event.target.closest('a[href]')) emit('navigate')
}
function handleKey(event: KeyboardEvent) {
  if (!props.mobile || !props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  }
  if (event.key !== 'Tab') return
  const controls = [
    ...(navigation.value?.querySelectorAll<HTMLElement>(
      'a[href], button:not(:disabled), input:not(:disabled)',
    ) ?? []),
  ].filter((el) => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
  const first = controls[0]
  const last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}
const filtered = computed(() =>
  store.sessions.filter((s) =>
    `${s.session_title} ${s.preview}`.toLowerCase().includes(search.value.trim().toLowerCase()),
  ),
)
function dateLabel(timestamp: number) {
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(
    timestamp * 1000,
  )
}
</script>
<template>
  <aside
    id="workspace-navigation"
    ref="navigation"
    class="sidebar"
    :role="mobile && open ? 'dialog' : undefined"
    :aria-modal="mobile && open ? true : undefined"
    aria-label="工作台导航"
    :inert="mobile && !open"
    :class="{ 'is-open': open }"
    @keydown="handleKey"
    @click="navigate"
  >
    <div class="sidebar-heading">
      <span>我的工作台</span
      ><button class="icon-button mobile-only" aria-label="收起导航" @click="$emit('close')">
        <AppIcon name="close" :size="18" />
      </button>
    </div>
    <button class="new-chat-button" @click="$emit('newChat')">
      <AppIcon name="plus" :size="18" />新建会话
    </button>
    <nav class="main-nav" aria-label="主导航">
      <RouterLink to="/chat"
        ><AppIcon name="chat" :size="18" />智能问答<span class="nav-dot"></span
      ></RouterLink>
      <RouterLink to="/knowledge"><AppIcon name="book" :size="18" />知识库</RouterLink>
      <RouterLink to="/runs"><AppIcon name="pulse" :size="18" />运行分析</RouterLink>
      <span class="nav-section-label">管理</span>
      <RouterLink to="/tools"><AppIcon name="layers" :size="18" />工具中心</RouterLink>
      <RouterLink to="/providers"><AppIcon name="server" :size="18" />模型供应商</RouterLink>
      <RouterLink to="/system"><AppIcon name="grid" :size="18" />系统概览</RouterLink>
    </nav>
    <div class="history-heading">
      <span>最近会话</span
      ><button
        class="icon-button"
        aria-label="刷新历史会话"
        title="刷新历史会话"
        :disabled="refreshing || store.loading"
        :aria-busy="refreshing"
        @click="refreshHistory"
      >
        <AppIcon name="refresh" :size="14" />
      </button>
    </div>
    <p v-if="refreshError" class="history-error" role="alert">
      {{ refreshError }}，可点击刷新重试。
    </p>
    <label class="history-search"
      ><AppIcon name="search" :size="15" /><input
        ref="searchInput"
        v-model="search"
        name="session-search"
        autocomplete="off"
        aria-label="搜索历史会话"
        placeholder="搜索记录…" /><button
        v-if="search"
        type="button"
        class="search-clear"
        aria-label="清除会话搜索"
        @click="clearSearch"
      >
        <AppIcon name="close" :size="14" /></button
    ></label>
    <div class="session-list" :aria-busy="refreshing || store.loading">
      <p v-if="refreshing || store.loading" class="sidebar-empty" role="status">正在读取会话…</p>
      <p v-if="!filtered.length && !refreshing && !store.loading" class="sidebar-empty">
        {{ search ? '没有匹配的会话' : '提问后，会话将保存在这里' }}
      </p>
      <button
        v-for="session in filtered"
        :key="session.session_id"
        class="session-item"
        :class="{ selected: store.currentId === session.session_id }"
        :aria-current="store.currentId === session.session_id ? 'true' : undefined"
        :title="session.session_title"
        @click="$emit('select', session.session_id)"
      >
        <AppIcon name="chat" :size="15" /><span>{{ session.session_title }}</span
        ><small>{{ dateLabel(session.updated_at) }}</small>
        <i v-if="store.conversations[session.session_id]?.activeRun" class="live-dot"></i>
      </button>
    </div>
    <div class="sidebar-bottom">
      <RouterLink to="/providers" class="environment-card">
        <span class="environment-icon"><AppIcon name="globe" :size="18" /></span>
        <div>
          <strong :title="store.profile?.label">{{ store.profile?.label || '尚未连接' }}</strong
          ><small>{{ store.profile?.configured ? '已配置 · 按需调用' : '模型尚未配置' }}</small>
        </div>
        <i class="live-dot" :class="{ offline: !store.system }"></i>
      </RouterLink>
      <div class="sidebar-footer">
        <span>本地工作空间</span><AppIcon name="shield" :size="14" />
      </div>
    </div>
  </aside>
</template>
