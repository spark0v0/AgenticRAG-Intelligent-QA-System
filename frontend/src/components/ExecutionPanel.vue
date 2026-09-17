<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useWorkbench } from '../stores/workbench'
import type { StageEvent, ToolEvent } from '../types'
import AppIcon from './AppIcon.vue'
import { sourceLabel } from '../composables/useRunAnalysis'
defineEmits<{ close: [] }>()
const props = defineProps<{ evidenceRequest?: { id: string; sequence: number } }>()
const panel = ref<HTMLElement>()
const store = useWorkbench()
const tab = ref('trace')
watch(
  () => props.evidenceRequest,
  async (request) => {
    if (!request) {
      tab.value = 'trace'
      return
    }
    tab.value = 'sources'
    await nextTick()
    const target = [...(panel.value?.querySelectorAll<HTMLElement>('[data-source]') ?? [])].find(
      (element) => element.dataset.source === request.id,
    )
    target?.scrollIntoView({ block: 'nearest' })
    target?.focus({ preventScroll: true })
  },
  { immediate: true },
)
const labels: Record<string, string> = {
  router: '意图路由',
  planner: '任务规划',
  retriever: '信息检索',
  generator: '答案生成',
  critic: '质量评审',
}
const statusLabels: Record<string, string> = {
  running: '执行中',
  success: '已完成',
  error: '失败',
  cancelled: '已取消',
  timeout: '超时',
}
const stages = computed(() => {
  const map = new Map<string, StageEvent>()
  store.selectedEvents.forEach((e) => {
    if (e.type === 'stage') map.set(e.data.stage_id, e)
  })
  return [...map.values()]
})
const tools = computed(() => {
  const map = new Map<string, ToolEvent>()
  store.selectedEvents.forEach((e) => {
    if (e.type === 'tool') map.set(e.data.call_id, e)
  })
  return [...map.values()]
})
const result = computed(() => store.selectedMessage?.result)
const sources = computed(
  () =>
    result.value?.source_map ??
    store.selectedEvents.findLast((e) => e.type === 'sources')?.data.items ??
    result.value?.sources.map((source, i) => ({
      citation_id: `来源 ${i + 1}`,
      source,
      excerpt: '',
    })) ??
    [],
)
const elapsed = computed(() => {
  const events = store.selectedEvents
  const start = events.find((e) => e.type === 'started')
  const end = events.findLast((e) => ['completed', 'error', 'cancelled'].includes(e.type))
  if (!start || !end) return undefined
  return (end.timestamp - start.timestamp).toFixed(1)
})
const rounds = computed(
  () => store.selectedEvents.filter((e) => e.type === 'retrieval_round').length,
)
function safeUrl(value: string) {
  try {
    const u = new URL(value)
    return ['http:', 'https:'].includes(u.protocol) ? u.href : undefined
  } catch {
    return undefined
  }
}
function format(value: unknown) {
  return JSON.stringify(value, null, 2)
}
</script>
<template>
  <aside ref="panel" class="execution-panel">
    <div class="panel-heading">
      <div><AppIcon name="pulse" :size="18" /><strong>执行详情</strong></div>
      <button
        class="icon-button"
        aria-label="收起执行详情"
        title="收起执行详情"
        @click="$emit('close')"
      >
        <AppIcon name="panel" :size="17" />
      </button>
    </div>
    <template v-if="!store.selectedMessage">
      <p class="empty-hint">暂无执行记录</p>
    </template>
    <template v-else>
      <div class="run-summary">
        <RouterLink
          v-if="store.selectedMessage.run_id"
          class="run-open"
          :to="{ path: '/runs', query: { run: store.selectedMessage.run_id } }"
          ><AppIcon name="diagonal" :size="15" />打开运行分析</RouterLink
        >
        <strong>{{
          result?.routing?.route === 'planning'
            ? '规划分析'
            : result?.routing?.route === 'retrieval'
              ? '检索增强'
              : result?.routing?.route === 'direct'
                ? '直接回答'
                : '本轮执行'
        }}</strong>
        <div>
          <span>{{ stages.length }} 个执行步骤</span><span v-if="elapsed">{{ elapsed }} s</span
          ><span v-if="rounds">{{ rounds }} 轮检索</span>
        </div>
        <small v-if="store.selectedMessage.run_id" class="run-id">{{
          store.selectedMessage.run_id.slice(0, 8)
        }}</small>
      </div>
      <div class="detail-tabs" role="tablist" aria-label="执行详情分类">
        <button
          v-for="item in [
            { id: 'trace', label: '执行过程', count: stages.length },
            { id: 'sources', label: '来源', count: sources.length },
            { id: 'tools', label: '工具', count: tools.length },
          ]"
          :key="item.id"
          role="tab"
          :aria-selected="tab === item.id"
          :class="{ active: tab === item.id }"
          @click="tab = item.id"
        >
          {{ item.label }}<span>{{ item.count }}</span>
        </button>
      </div>
      <div class="detail-content">
        <template v-if="tab === 'trace'">
          <p v-if="!stages.length" class="empty-hint">
            {{ store.busy ? '正在建立本轮执行记录…' : '此历史记录没有保存执行详情。' }}
          </p>
          <div class="timeline">
            <details
              v-for="event in stages"
              :key="event.data.stage_id"
              class="timeline-item"
              :class="event.data.status"
            >
              <summary>
                <span class="timeline-dot"
                  ><AppIcon
                    :name="
                      event.data.status === 'success'
                        ? 'check'
                        : event.data.status === 'error'
                          ? 'close'
                          : 'clock'
                    "
                    :size="12" /></span
                ><span class="stage-title"
                  >{{ labels[event.data.node] || event.data.node
                  }}<small
                    >{{ event.data.node
                    }}<template v-if="event.data.round > 1">
                      · 第 {{ event.data.round }} 轮</template
                    ></small
                  ></span
                ><span class="stage-time">{{
                  event.data.duration_ms != null
                    ? `${event.data.duration_ms.toFixed(0)} ms`
                    : statusLabels[event.data.status]
                }}</span>
              </summary>
              <div class="stage-content">
                <span class="tiny-label">输入摘要</span>
                <p>{{ event.data.input }}</p>
                <span class="tiny-label">输出 · {{ statusLabels[event.data.status] }}</span>
                <p>{{ event.data.output || '暂无输出' }}</p>
                <details v-if="event.data.metadata" class="raw-details">
                  <summary>查看结构化记录</summary>
                  <pre>{{ format(event.data.metadata) }}</pre>
                </details>
              </div>
            </details>
          </div>
          <div v-if="result?.evaluation_score != null" class="assessment">
            <div>
              <AppIcon name="check" :size="16" /><strong>评审参考</strong
              ><span>{{ (result.evaluation_score * 100).toFixed(0) }} / 100</span>
            </div>
            <p>基于现有规则的质量评分，非事实准确率。</p>
            <ul v-if="result.critic_suggestions?.length">
              <li v-for="tip in result.critic_suggestions" :key="tip">{{ tip }}</li>
            </ul>
          </div>
        </template>
        <template v-else-if="tab === 'sources'"
          ><p v-if="!sources.length" class="empty-hint">
            本轮没有引用来源。直接回答或旧记录可能没有来源信息。
          </p>
          <article
            v-for="source in sources"
            :key="source.citation_id"
            class="source-card"
            :data-source="source.citation_id"
            tabindex="-1"
          >
            <div>
              <span class="citation-id">{{ source.citation_id }}</span
              ><AppIcon name="book" :size="16" />
            </div>
            <a
              v-if="safeUrl(source.source)"
              :href="safeUrl(source.source)"
              target="_blank"
              rel="noopener noreferrer"
              >{{ sourceLabel(source.source) }}<AppIcon name="external" :size="12" /></a
            ><strong v-else>{{ sourceLabel(source.source) }}</strong>
            <p>{{ source.excerpt || '当前记录只有来源标识，没有保存证据片段。' }}</p>
          </article></template
        >
        <template v-else
          ><p v-if="!tools.length" class="empty-hint">本轮尚无工具调用记录。</p>
          <details v-for="event in tools" :key="event.data.call_id" class="tool-call">
            <summary>
              <AppIcon name="layers" :size="16" /><strong>{{ event.data.tool }}</strong
              ><span :class="event.data.status">{{
                statusLabels[event.data.status] || event.data.status
              }}</span>
            </summary>
            <small>{{ event.data.protocol }} · {{ event.data.duration_ms ?? '—' }} ms</small>
            <p v-if="event.data.error" class="inline-error">{{ event.data.error }}</p>
            <span class="tiny-label">输入参数</span>
            <pre>{{ format(event.data.input) }}</pre>
            <span class="tiny-label">输出摘要</span>
            <pre>{{ format(event.data.output || []) }}</pre>
          </details></template
        >
      </div>
    </template>
  </aside>
</template>
