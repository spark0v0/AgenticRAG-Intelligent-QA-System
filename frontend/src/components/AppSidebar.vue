<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElDropdown, ElDropdownMenu, ElDropdownItem, ElMessageBox } from 'element-plus'
import 'element-plus/es/components/dropdown/style/css'
import 'element-plus/es/components/dropdown-menu/style/css'
import 'element-plus/es/components/dropdown-item/style/css'
import 'element-plus/es/components/message-box/style/css'
import { api } from '../api/client'
import { exportConversation } from '../chat/export'
import type { SessionSummary } from '../types'
import { useWorkbench } from '../stores/workbench'
import AppIcon from './AppIcon.vue'
const props = defineProps<{ open: boolean; mobile: boolean }>()
const emit = defineEmits<{ newChat: []; select: [id: string]; close: []; navigate: [] }>()
const store = useWorkbench()
const search = ref(store.sessionSearch)
const searchInput = ref<HTMLInputElement>()
const navigation = ref<HTMLElement>()
const refreshing = ref(false)
const refreshError = ref('')
let refreshController: AbortController | undefined
const actionController = new AbortController()
const actionBusy = ref('')
const feedback = ref('')
let searchTimer: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => {
  refreshController?.abort()
  actionController.abort()
  clearTimeout(searchTimer)
})
watch(search, (value) => {
  refreshController?.abort()
  clearTimeout(searchTimer)
  store.resetSessionSearch(value)
  searchTimer = setTimeout(() => void refreshHistory(), 250)
})
async function refreshHistory() {
  refreshController?.abort()
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
    if (refreshController === controller) refreshing.value = false
  }
}
async function more() {
  refreshError.value = ''
  try {
    await store.moreSessions(actionController.signal)
  } catch (cause) {
    if (!actionController.signal.aborted)
      refreshError.value = cause instanceof Error ? cause.message : '加载失败'
  }
}
async function act(command: string, session: SessionSummary) {
  if (actionBusy.value) return
  actionBusy.value = session.session_id
  feedback.value = ''
  refreshError.value = ''
  try {
    if (command === 'rename') {
      const result = await ElMessageBox.prompt('为这段对话设置一个便于查找的名称', '重命名会话', {
        inputValue: session.session_title,
        inputValidator: (value) =>
          (!!value?.trim() && value.trim().length <= 80) || '请输入 1–80 个字符',
        confirmButtonText: '保存',
        cancelButtonText: '取消',
      })
      if (actionController.signal.aborted) return
      await store.updateSession(
        session.session_id,
        { title: result.value.trim() },
        actionController.signal,
      )
      feedback.value = '会话名称已保存'
    } else if (command === 'pin') {
      await store.updateSession(
        session.session_id,
        { pinned: !session.pinned },
        actionController.signal,
      )
      feedback.value = session.pinned ? '会话已置顶' : '已取消置顶'
    } else if (command === 'delete') {
      await ElMessageBox.confirm(
        `删除“${session.session_title}”及其消息和运行记录？此操作无法撤销，知识库文档不受影响。`,
        '删除会话',
        { type: 'warning', confirmButtonText: '删除', cancelButtonText: '保留' },
      )
      if (actionController.signal.aborted) return
      await store.deleteSession(session.session_id, actionController.signal)
      feedback.value = '会话已删除'
      await nextTick()
      navigation.value?.querySelector<HTMLButtonElement>('.new-chat-button')?.focus()
    } else if (command === 'export') {
      const detail = await api.session(session.session_id, actionController.signal)
      if (!actionController.signal.aborted) {
        exportConversation(detail)
        feedback.value = '对话已导出为 Markdown，包含问题与回答，请按需保管'
      }
    }
  } catch (cause) {
    if (!actionController.signal.aborted && cause !== 'cancel' && cause !== 'close')
      refreshError.value = cause instanceof Error ? cause.message : '操作失败，请重试'
  } finally {
    actionBusy.value = ''
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
    <p v-if="feedback" class="history-feedback" role="status">{{ feedback }}</p>
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
      <div v-for="session in filtered" :key="session.session_id" class="session-row">
        <button
          class="session-item"
          :class="{ selected: store.currentId === session.session_id }"
          :aria-current="store.currentId === session.session_id ? 'true' : undefined"
          :title="session.session_title"
          @click="$emit('select', session.session_id)"
        >
          <AppIcon :name="session.pinned ? 'pin' : 'chat'" :size="15" /><span>{{
            session.session_title
          }}</span
          ><small>{{ dateLabel(session.updated_at) }}</small>
          <i v-if="store.conversations[session.session_id]?.activeRun" class="live-dot"></i>
        </button>
        <ElDropdown trigger="click" @command="act($event, session)">
          <button
            class="icon-button session-actions"
            :aria-label="`会话操作：${session.session_title}`"
            :disabled="!!actionBusy"
          >
            <AppIcon name="more" :size="15" />
          </button>
          <template #dropdown
            ><ElDropdownMenu>
              <ElDropdownItem command="rename">重命名</ElDropdownItem>
              <ElDropdownItem command="pin">{{
                session.pinned ? '取消置顶' : '置顶会话'
              }}</ElDropdownItem>
              <ElDropdownItem command="export">导出 Markdown</ElDropdownItem>
              <ElDropdownItem
                command="delete"
                divided
                :disabled="!!store.conversations[session.session_id]?.activeRun"
                >删除会话</ElDropdownItem
              >
            </ElDropdownMenu></template
          >
        </ElDropdown>
      </div>
      <button
        v-if="store.sessions.length < store.sessionsTotal"
        class="history-more"
        :disabled="store.loadingMore || refreshing"
        @click="more"
      >
        {{ store.loadingMore ? '正在加载…' : '加载更多会话' }}
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
