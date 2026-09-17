<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { requestJson } from '../api/client'
import { useWorkbench } from '../stores/workbench'
import {
  useRunAnalysis,
  nodeLabels,
  runLabels,
  durationLabel,
  sourceLabel,
  safeSourceUrl,
} from '../composables/useRunAnalysis'
import type { RunDetail, RunRecord } from '../types'
import AppIcon from '../components/AppIcon.vue'
const MarkdownContent = defineAsyncComponent(() => import('../components/MarkdownContent.vue'))
const route = useRoute()
const router = useRouter()
const store = useWorkbench()
const items = ref<RunRecord[]>([])
const total = ref(0)
const page = ref(0)
const search = ref('')
const status = ref('')
const error = ref('')
const loading = ref(false)
const run = ref<RunDetail>()
const selectedStage = ref('')
const tab = ref('trace')
const { stages, tools, sources, duration, span, bar } = useRunAnalysis(run)
const stage = computed(
  () => stages.value.find((e) => e.data.stage_id === selectedStage.value) ?? stages.value[0],
)
const stageTools = computed(() =>
  tools.value.filter(
    (t) =>
      stage.value &&
      t.data.started_at >= stage.value.data.started_at &&
      (!stage.value.data.finished_at || t.data.started_at <= stage.value.data.finished_at),
  ),
)
let listController: AbortController | undefined
let detailController: AbortController | undefined
let poll: ReturnType<typeof setTimeout> | undefined
let debounce: ReturnType<typeof setTimeout> | undefined
let detailVersion = 0
let listVersion = 0
let disposed = false
async function loadList() {
  listController?.abort()
  listController = new AbortController()
  const version = ++listVersion
  loading.value = true
  error.value = ''
  try {
    const result = await requestJson<{ items: RunRecord[]; total: number }>(
      `/runs?${new URLSearchParams({ search: search.value, status: status.value, offset: String(page.value * 20), limit: '20' })}`,
      { signal: listController.signal },
    )
    if (version !== listVersion) return
    items.value = result.items
    total.value = result.total
    if (!route.query.run && items.value[0])
      await router.replace({ query: { run: items.value[0].id } })
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError') && version === listVersion)
      error.value = e instanceof Error ? e.message : '读取失败'
  } finally {
    if (version === listVersion) loading.value = false
  }
}
async function loadDetail(id: string, background = false) {
  detailController?.abort()
  detailController = new AbortController()
  const version = ++detailVersion
  clearTimeout(poll)
  if (!background) {
    run.value = undefined
    selectedStage.value = ''
    error.value = ''
  }
  try {
    const result = await requestJson<RunDetail>(`/runs/${encodeURIComponent(id)}`, {
      signal: detailController.signal,
    })
    if (version !== detailVersion || disposed) return
    run.value = result
    if (result.status === 'running') poll = setTimeout(() => void loadDetail(id, true), 2000)
    else if (background) void loadList()
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError') && version === detailVersion)
      error.value = e instanceof Error ? e.message : '读取失败'
  }
}
watch(
  () => route.query.run,
  (id) => {
    if (typeof id === 'string') void loadDetail(id)
  },
  { immediate: true },
)
watch([search, status], () => {
  page.value = 0
  clearTimeout(debounce)
  debounce = setTimeout(() => void loadList(), 250)
})
watch(page, () => void loadList())
onMounted(loadList)
onUnmounted(() => {
  disposed = true
  detailVersion++
  listVersion++
  clearTimeout(poll)
  clearTimeout(debounce)
  listController?.abort()
  detailController?.abort()
})
function time(value: number) {
  return new Date(value * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
async function openChat() {
  if (!run.value) return
  await store.loadSession(run.value.session_id)
  store.selectedRun = run.value.id
  await router.push('/chat')
}
function exportRun() {
  if (!run.value) return
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(run.value, null, 2)], { type: 'application/json' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `run-${run.value.id.slice(0, 8)}.json`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
function refresh() {
  void loadList()
  if (typeof route.query.run === 'string') void loadDetail(route.query.run, true)
}
</script>
<template>
  <main class="runs-page">
    <div class="page-title">
      <div>
        <span class="eyebrow">OBSERVABILITY</span>
        <h1>运行分析<span class="heading-dot coral"></span></h1>
        <p>从一次提问，到每一步执行。</p>
      </div>
      <button class="secondary-button" :disabled="loading" @click="refresh">
        <AppIcon name="refresh" :size="16" />刷新
      </button>
    </div>
    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <div class="runs-layout">
      <section class="runs-index" aria-label="运行列表">
        <label class="search-field"
          ><AppIcon name="search" :size="16" /><input
            v-model="search"
            aria-label="搜索运行"
            placeholder="搜索问题…"
        /></label>
        <div class="run-filters">
          <button
            v-for="item in [
              { id: '', label: '全部' },
              { id: 'success', label: '完成' },
              { id: 'error', label: '失败' },
              { id: 'cancelled', label: '取消' },
            ]"
            :key="item.id"
            :class="{ active: status === item.id }"
            @click="status = item.id"
          >
            {{ item.label }}
          </button>
        </div>
        <div class="run-index-list">
          <button
            v-for="item in items"
            :key="item.id"
            class="run-index-item"
            :class="{ selected: route.query.run === item.id }"
            @click="router.replace({ query: { run: item.id } })"
          >
            <span class="run-index-meta"
              ><span class="status-indicator" :class="item.status"></span>{{ runLabels[item.status]
              }}<time>{{ time(item.started_at) }}</time></span
            ><strong>{{ item.query || '图片问答' }}</strong
            ><span class="run-index-bottom"
              ><code>{{ item.id.slice(0, 8) }}</code
              ><span>{{
                durationLabel(
                  item.finished_at ? (item.finished_at - item.started_at) * 1000 : undefined,
                )
              }}</span></span
            >
          </button>
          <p v-if="!items.length" class="empty-hint">
            {{ loading ? '正在读取…' : '没有匹配的运行记录' }}
          </p>
        </div>
        <footer class="pagination">
          <span>{{ total }} 条</span
          ><button class="icon-button" aria-label="上一页" :disabled="page === 0" @click="page--">
            <AppIcon name="right" :size="14" class="rotate-back" /></button
          ><span>{{ page + 1 }}</span
          ><button
            class="icon-button"
            aria-label="下一页"
            :disabled="(page + 1) * 20 >= total"
            @click="page++"
          >
            <AppIcon name="right" :size="14" />
          </button>
        </footer>
      </section>
      <section v-if="run" class="run-detail">
        <header class="run-detail-heading">
          <span
            class="status-badge"
            :class="{ ready: run.status === 'success', failed: run.status === 'error' }"
            >{{ runLabels[run.status] }}</span
          ><code>RUN / {{ run.id.slice(0, 8) }}</code>
          <div>
            <button
              class="icon-button"
              title="导出运行 JSON（含问题与回答）"
              aria-label="导出运行记录"
              @click="exportRun"
            >
              <AppIcon name="download" :size="17" /></button
            ><button class="text-action" @click="openChat">
              回到会话<AppIcon name="diagonal" :size="16" />
            </button>
          </div>
        </header>
        <h2 class="run-question">{{ run.query || '图片问答' }}</h2>
        <div class="run-metrics">
          <div>
            <span>执行总耗时</span><strong>{{ durationLabel(duration) }}</strong>
          </div>
          <div>
            <span>执行节点</span><strong>{{ stages.length }}<small>个</small></strong>
          </div>
          <div>
            <span>来源 / 工具调用</span
            ><strong>{{ sources.length }}<small>/</small>{{ tools.length }}</strong>
          </div>
          <div>
            <span>生成轮次</span
            ><strong
              >{{ run.events.filter((e) => e.type === 'answer_start').length
              }}<small>轮</small></strong
            >
          </div>
        </div>
        <p v-if="run.error" class="inline-error">{{ run.error }}</p>
        <div class="analysis-tabs" role="tablist" aria-label="运行分析分类">
          <button
            v-for="item in [
              { id: 'trace', icon: 'branch', label: '执行瀑布' },
              { id: 'sources', icon: 'book', label: '证据来源' },
              { id: 'answer', icon: 'chat', label: '最终回答' },
            ]"
            :key="item.id"
            role="tab"
            :aria-selected="tab === item.id"
            :class="{ active: tab === item.id }"
            @click="tab = item.id"
          >
            <AppIcon :name="item.icon" :size="16" />{{ item.label }}
          </button>
        </div>
        <div v-if="tab === 'trace'" class="analysis-content">
          <div class="waterfall-heading">
            <span>节点 / 轮次</span
            ><span
              >0<span>{{ durationLabel(span) }}</span></span
            ><span>耗时</span>
          </div>
          <div class="waterfall">
            <button
              v-for="event in stages"
              :key="event.data.stage_id"
              class="waterfall-row"
              :class="{ selected: stage?.data.stage_id === event.data.stage_id }"
              @click="selectedStage = event.data.stage_id"
            >
              <span class="waterfall-node"
                ><i class="status-indicator" :class="event.data.status"></i
                ><span
                  >{{ nodeLabels[event.data.node] || event.data.node
                  }}<small>{{ event.data.node }} · {{ event.data.round }}</small></span
                ></span
              ><span class="waterfall-track"
                ><i :class="event.data.node" :style="bar(event)"></i></span
              ><span class="waterfall-time">{{ durationLabel(event.data.duration_ms) }}</span>
            </button>
          </div>
          <p v-if="!stages.length" class="empty-hint">该记录尚无节点数据。</p>
          <section v-if="stage" class="node-inspector">
            <header>
              <span class="node-icon"><AppIcon name="branch" :size="19" /></span>
              <div>
                <h3>{{ nodeLabels[stage.data.node] || stage.data.node }}</h3>
                <span
                  >第 {{ stage.data.round }} 轮 ·
                  {{ runLabels[stage.data.status] || stage.data.status }}</span
                >
              </div>
              <span class="subtle-badge">{{ durationLabel(stage.data.duration_ms) }}</span>
            </header>
            <div class="node-io">
              <div>
                <span class="tiny-label">INPUT / 输入摘要</span>
                <p>{{ stage.data.input || '未记录' }}</p>
              </div>
              <div>
                <span class="tiny-label">OUTPUT / 输出摘要</span>
                <p>{{ stage.data.output || '暂无输出' }}</p>
              </div>
            </div>
            <details v-if="stage.data.metadata" class="raw-details">
              <summary>结构化节点数据</summary>
              <pre>{{ JSON.stringify(stage.data.metadata, null, 2) }}</pre>
            </details>
            <div v-if="stageTools.length" class="node-tools">
              <span class="tiny-label">节点期间的工具调用</span>
              <details v-for="tool in stageTools" :key="tool.data.call_id" class="tool-call">
                <summary>
                  <AppIcon name="tool" :size="15" /><strong>{{ tool.data.tool }}</strong
                  ><span>{{ runLabels[tool.data.status] || tool.data.status }}</span>
                </summary>
                <small>{{ tool.data.protocol }} · {{ durationLabel(tool.data.duration_ms) }}</small>
                <p v-if="tool.data.error" class="inline-error">{{ tool.data.error }}</p>
                <pre>{{
                  JSON.stringify({ input: tool.data.input, output: tool.data.output }, null, 2)
                }}</pre>
              </details>
            </div>
          </section>
        </div>
        <div v-else-if="tab === 'sources'" class="analysis-content evidence-grid">
          <article v-for="source in sources" :key="source.citation_id" class="evidence-item">
            <header>
              <span class="citation-id">{{ source.citation_id }}</span
              ><AppIcon name="book" :size="17" />
            </header>
            <a
              v-if="safeSourceUrl(source.source)"
              :href="safeSourceUrl(source.source)"
              target="_blank"
              rel="noopener noreferrer"
              >{{ sourceLabel(source.source) }}<AppIcon name="external" :size="13"
            /></a>
            <h3 v-else>{{ sourceLabel(source.source) }}</h3>
            <p>{{ source.excerpt || '此来源未保存证据片段。' }}</p>
          </article>
          <p v-if="!sources.length" class="empty-hint">本轮未记录来源；直接回答可能不经过检索。</p>
        </div>
        <div v-else class="analysis-content run-answer">
          <p v-if="run.status !== 'success'" class="notice">本轮未完成，以下为已保存的草稿。</p>
          <MarkdownContent
            v-if="run.result?.answer"
            :content="run.result.answer"
            :streaming="false"
          />
          <p v-else class="empty-hint">本轮尚未保存回答。</p>
          <div v-if="run.result?.critic_feedback" class="assessment">
            <strong>评审参考 · 规则评分</strong>
            <p>{{ run.result.critic_feedback }}</p>
          </div>
        </div>
      </section>
      <section v-else class="run-detail run-empty">
        <AppIcon name="branch" :size="40" />
        <h2>{{ route.query.run ? '正在读取运行记录' : '暂无运行记录' }}</h2>
        <RouterLink class="secondary-button" to="/chat"
          >前往问答<AppIcon name="right" :size="15"
        /></RouterLink>
      </section>
    </div>
  </main>
</template>
