<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useWorkbench } from '../stores/workbench'
import { useAutoScroll } from '../composables/useAutoScroll'
import AppIcon from '../components/AppIcon.vue'
import ChatComposer from '../components/ChatComposer.vue'
import MessageBubble from '../components/MessageBubble.vue'
const ExecutionPanel = defineAsyncComponent(() => import('../components/ExecutionPanel.vue'))
const store = useWorkbench()
const scroller = ref<HTMLElement | null>(null)
const showPanel = ref(false)
const contentKey = computed(
  () =>
    `${store.currentId}:${store.current?.messages.length}:${store.current?.messages.at(-1)?.content.length}:${store.current?.status}`,
)
const { following, onScroll, toBottom } = useAutoScroll(scroller, () => contentKey.value)
watch(
  () => store.currentId,
  () => {
    void toBottom()
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
  {
    icon: 'spark',
    title: '从一个问题开始',
    description: '你好，请介绍一下你能做什么',
    text: '你好，请介绍一下你能做什么',
  },
]
function inspect(runId: string) {
  store.selectedRun = runId
  showPanel.value = true
}
</script>
<template>
  <main class="chat-workspace">
    <section class="conversation-pane">
      <div class="conversation-heading">
        <div>
          <span class="live-dot" :class="{ offline: !store.system }"></span
          ><span>{{ store.current?.messages.length ? store.current.title : '新会话' }}</span
          ><span v-if="store.busy" class="status-pill">运行中</span>
        </div>
        <button
          class="icon-button"
          :aria-label="showPanel ? '收起执行详情' : '展开执行详情'"
          title="执行详情"
          @click="showPanel = !showPanel"
        >
          <AppIcon name="panel" :size="18" />
        </button>
      </div>
      <div ref="scroller" class="conversation-scroll" @scroll="onScroll">
        <div v-if="store.loadingSession" class="loading-session" role="status">正在恢复会话…</div>
        <div v-else-if="!store.current?.messages.length" class="welcome">
          <div class="workspace-label"><span></span> YOUR RESEARCH SPACE</div>
          <h1>AgenticRAG<span>智能问答与检索</span></h1>
          <div class="welcome-model">
            <AppIcon name="server" :size="15" />{{ store.profile?.label || '尚未选择模型'
            }}<span class="status-badge" :class="{ ready: store.profile?.configured }">{{
              store.profile?.configured ? '已配置' : '待配置'
            }}</span>
          </div>
          <div class="suggestion-heading">开始探索 <span>01 — 04</span></div>
          <div class="suggestion-grid">
            <button
              v-for="prompt in prompts"
              :key="prompt.title"
              :disabled="!store.system || store.loading"
              @click="store.current && (store.current.draft = prompt.text)"
            >
              <span class="suggestion-icon"><AppIcon :name="prompt.icon" :size="20" /></span
              ><strong>{{ prompt.title }}</strong>
              <p>{{ prompt.description }}</p>
              <AppIcon name="diagonal" :size="17" />
            </button>
          </div>
          <div class="workspace-links">
            <RouterLink to="/runs"
              ><AppIcon name="pulse" :size="16" />运行记录<AppIcon
                name="right"
                :size="14" /></RouterLink
            ><RouterLink to="/providers"
              ><AppIcon name="settings" :size="16" />模型供应商<AppIcon name="right" :size="14"
            /></RouterLink>
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
      <button
        v-if="!following && store.current?.messages.length"
        class="scroll-bottom"
        @click="toBottom()"
      >
        <AppIcon name="down" :size="14" />回到底部
      </button>
      <ChatComposer />
    </section>
    <div v-if="showPanel" class="panel-container">
      <ExecutionPanel @close="showPanel = false" />
    </div>
  </main>
</template>
