<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElDrawer } from 'element-plus'
import 'element-plus/es/components/drawer/style/css'
import { useWorkbench } from '../stores/workbench'
import { useAutoScroll } from '../composables/useAutoScroll'
import AppIcon from '../components/AppIcon.vue'
import ChatComposer from '../components/ChatComposer.vue'
import MessageBubble from '../components/MessageBubble.vue'
const ExecutionPanel = defineAsyncComponent(() => import('../components/ExecutionPanel.vue'))
const store = useWorkbench()
const scroller = ref<HTMLElement | null>(null)
const showPanel = ref(false)
const compactQuery = window.matchMedia('(max-width: 1000px)')
const compact = ref(compactQuery.matches)
let panelTrigger: HTMLElement | undefined
function rememberTrigger() {
  if (document.activeElement instanceof HTMLElement) panelTrigger = document.activeElement
}
function restorePanelFocus() {
  if (!showPanel.value && panelTrigger?.isConnected) panelTrigger.focus({ preventScroll: true })
}
async function closePanel() {
  showPanel.value = false
  if (!compact.value) {
    await nextTick()
    restorePanelFocus()
  }
}
function togglePanel() {
  if (showPanel.value) void closePanel()
  else {
    rememberTrigger()
    showPanel.value = true
  }
}
function onLayoutChange(event: MediaQueryListEvent) {
  showPanel.value = false
  compact.value = event.matches
  void nextTick(restorePanelFocus)
}
onMounted(() => compactQuery.addEventListener('change', onLayoutChange))
onUnmounted(() => compactQuery.removeEventListener('change', onLayoutChange))
const evidenceRequest = ref<{ id: string; sequence: number }>()
const empty = computed(() => !store.current?.messages.length && !store.loadingSession)
const contentKey = computed(
  () =>
    `${store.currentId}:${store.current?.messages.length}:${store.current?.messages.at(-1)?.content.length}:${store.current?.status}`,
)
const { following, onScroll, toBottom } = useAutoScroll(
  scroller,
  () => contentKey.value,
  () => !!store.current?.messages.length,
)
watch(
  () => store.currentId,
  async () => {
    showPanel.value = false
    panelTrigger = undefined
    evidenceRequest.value = undefined
    following.value = true
    await nextTick()
    if (store.current?.messages.length) await toBottom()
    else if (scroller.value) scroller.value.scrollTop = 0
  },
)
const prompts = [
  {
    icon: 'layers',
    title: '理解复杂概念',
    description: 'AgenticRAG 与传统 RAG 有何区别？',
    text: 'AgenticRAG 与传统 RAG 有什么区别？',
  },
  {
    icon: 'book',
    title: '探索本地知识',
    description: '智能问答系统包含哪些核心模块？',
    text: '请介绍智能问答系统的核心组成',
  },
  {
    icon: 'code',
    title: '分析技术方案',
    description: '如何设计可靠的流式问答交互？',
    text: '如何设计可靠的流式问答交互？',
  },
]
function inspect(runId: string, sourceId?: string) {
  rememberTrigger()
  store.selectedRun = runId
  evidenceRequest.value = sourceId
    ? { id: sourceId, sequence: (evidenceRequest.value?.sequence ?? 0) + 1 }
    : undefined
  showPanel.value = true
}
function choosePrompt(text: string) {
  if (!store.current) return
  store.current.draft = text
  scroller.value?.querySelector<HTMLTextAreaElement>('textarea')?.focus()
}
</script>
<template>
  <main class="chat-workspace">
    <section class="conversation-pane" :class="{ 'is-empty': empty }">
      <div v-if="!empty || showPanel" class="conversation-heading">
        <div>
          <span class="live-dot" :class="{ offline: !store.system }"></span
          ><span>{{ store.current?.messages.length ? store.current.title : '新会话' }}</span
          ><span v-if="store.busy" class="status-pill">运行中</span>
        </div>
        <button
          class="icon-button"
          :aria-label="showPanel ? '收起执行详情' : '展开执行详情'"
          :aria-expanded="showPanel"
          aria-controls="chat-execution-details"
          title="执行详情"
          @click="togglePanel"
        >
          <AppIcon name="panel" :size="18" />
        </button>
      </div>
      <div ref="scroller" class="conversation-scroll" @scroll="onScroll">
        <div v-if="store.loadingSession" class="loading-session" role="status">正在恢复会话…</div>
        <div v-else-if="!store.current?.messages.length" class="welcome">
          <div class="welcome-intro">
            <h1>开始一个新问题</h1>
            <p class="welcome-description">查阅本地资料，结合网络信息，让每个问题都有据可循。</p>
          </div>
          <RouterLink
            v-if="store.system && !store.profile?.configured"
            class="configure-model secondary-button"
            to="/providers"
            ><AppIcon name="settings" :size="17" />配置可用模型</RouterLink
          >
          <ChatComposer />
          <div class="suggestion-heading">
            <h2>试着问一问</h2>
            <span>选择一个问题，继续编辑后发送</span>
          </div>
          <div class="suggestion-grid" aria-label="建议问题">
            <button
              v-for="prompt in prompts"
              :key="prompt.title"
              :disabled="!store.system || store.loading"
              @click="choosePrompt(prompt.text)"
            >
              <AppIcon :name="prompt.icon" :size="19" />
              <span class="suggestion-copy"
                ><strong>{{ prompt.description }}</strong
                ><small>{{ prompt.title }}</small></span
              >
              <span class="suggestion-use">填入问题<AppIcon name="right" :size="16" /></span>
            </button>
          </div>
          <div class="workspace-links">
            <RouterLink to="/knowledge"
              ><AppIcon name="book" :size="15" />管理我的知识库</RouterLink
            >
            <RouterLink to="/runs"><AppIcon name="pulse" :size="15" />查看运行记录</RouterLink>
          </div>
        </div>
        <div v-else class="messages">
          <MessageBubble
            v-for="message in store.current.messages"
            :key="message.id"
            :message="message"
            :selected="store.selectedRun === message.run_id"
            @inspect="inspect"
          />
        </div>
      </div>
      <div v-if="!following && store.current?.messages.length" class="scroll-return">
        <button class="scroll-bottom" @click="toBottom()">
          <AppIcon name="down" :size="14" />回到底部
        </button>
      </div>
      <ChatComposer v-if="!empty" />
    </section>
    <div v-if="showPanel && !compact" id="chat-execution-details" class="panel-container">
      <ExecutionPanel :evidence-request="evidenceRequest" @close="closePanel" />
    </div>
    <ElDrawer
      v-if="compact"
      v-model="showPanel"
      title="执行详情"
      :with-header="false"
      size="min(420px, 100vw)"
      class="execution-drawer"
      append-to-body
      destroy-on-close
      @closed="restorePanelFocus"
    >
      <ExecutionPanel
        id="chat-execution-details"
        :evidence-request="evidenceRequest"
        @close="closePanel"
      />
    </ElDrawer>
  </main>
</template>
