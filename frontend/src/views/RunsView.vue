<script setup lang="ts">
import EvidenceButton from '../components/knowledge/EvidenceButton.vue'
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { requestJson } from '../api/client'
import { useWorkbench } from '../stores/workbench'
import {
  useRunAnalysis,
  runLabels,
  durationLabel,
  sourceLabel,
  safeSourceUrl,
} from '../composables/useRunAnalysis'
import type { RunDetail, RunRecord } from '../types'
import AppIcon from '../components/AppIcon.vue'
import RunWaterfall from '../components/runs/RunWaterfall.vue'
import RunNodeDetail from '../components/runs/RunNodeDetail.vue'
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
const mobileDetail = ref(typeof route.query.run === 'string')
const detailRoot = ref<HTMLElement>()
const detailLoading = ref(false)
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
    if (disposed || version !== listVersion) return
    items.value = result.items
    total.value = result.total
    if (!route.query.run && items.value[0] && !window.matchMedia('(max-width: 1000px)').matches)
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
    detailLoading.value = true
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
  } finally {
    if (!disposed && version === detailVersion) detailLoading.value = false
  }
}
watch(
  () => route.query.run,
  (id) => {
    if (typeof id === 'string') {
      mobileDetail.value = true
      void loadDetail(id)
    } else {
      detailVersion++
      detailController?.abort()
      clearTimeout(poll)
      run.value = undefined
      mobileDetail.value = false
    }
  },
  { immediate: true },
)
watch([search, status], () => {
  clearTimeout(debounce)
  listController?.abort()
  listVersion++
  debounce = setTimeout(() => {
    if (page.value === 0) void loadList()
    else page.value = 0
  }, 250)
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
async function selectRun(id: string) {
  mobileDetail.value = true
  if (route.query.run !== id) await router.replace({ query: { ...route.query, run: id } })
  await nextTick()
  detailRoot.value?.focus({ preventScroll: true })
  detailRoot.value?.scrollIntoView({ block: 'start' })
}
async function backToList() {
  mobileDetail.value = false
  await nextTick()
  document.querySelector<HTMLElement>('.run-index-item.selected')?.focus()
}
async function showCitation(id: string) {
  tab.value = 'sources'
  await nextTick()
  const target = [...(detailRoot.value?.querySelectorAll<HTMLElement>('[data-source]') ?? [])].find(
    (element) => element.dataset.source === id,
  )
  target?.scrollIntoView({ block: 'nearest' })
  target?.focus({ preventScroll: true })
}
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
        <h1>运行分析</h1>
      </div>
      <button class="secondary-button" :disabled="loading" @click="refresh">
        <AppIcon name="refresh" :size="16" />刷新
      </button>
    </div>
    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <div class="runs-layout" :class="{ 'show-detail': mobileDetail }">
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
            @click="selectRun(item.id)"
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
      <section v-if="run" ref="detailRoot" class="run-detail" tabindex="-1">
        <button class="text-action runs-back" @click="backToList">
          <AppIcon name="right" :size="16" class="rotate-back" />返回运行列表
        </button>
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
          <RunWaterfall
            :stages="stages"
            :selected="stage?.data.stage_id"
            :span="span"
            :bar="bar"
            @select="selectedStage = $event"
          />
          <RunNodeDetail v-if="stage" :stage="stage" :tools="stageTools" />
        </div>
        <div v-else-if="tab === 'sources'" class="analysis-content evidence-grid">
          <article
            v-for="source in sources"
            :key="source.citation_id"
            class="evidence-item"
            :data-source="source.citation_id"
            tabindex="-1"
          >
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
            <EvidenceButton :source="source" />
          </article>
          <p v-if="!sources.length" class="empty-hint">本轮未记录来源；直接回答可能不经过检索。</p>
        </div>
        <div v-else class="analysis-content run-answer">
          <p v-if="run.status !== 'success'" class="notice">本轮未完成，以下为已保存的草稿。</p>
          <MarkdownContent
            v-if="run.result?.answer"
            :content="run.result.answer"
            :streaming="false"
            :sources="run.result.source_map"
            @citation="showCitation"
          />
          <p v-else class="empty-hint">本轮尚未保存回答。</p>
          <div v-if="run.result?.critic_feedback" class="assessment">
            <strong>{{
              run.result?.evaluation ? '证据检查 · 非事实准确率' : '历史评审参考 · 规则评分'
            }}</strong>
            <p>{{ run.result.critic_feedback }}</p>
          </div>
        </div>
      </section>
      <section v-else ref="detailRoot" class="run-detail run-empty" tabindex="-1">
        <button class="text-action runs-back" @click="backToList">
          <AppIcon name="right" :size="16" class="rotate-back" />返回运行列表
        </button>
        <AppIcon name="branch" :size="40" />
        <h2>
          {{
            detailLoading
              ? '正在读取运行记录'
              : error
                ? '运行记录读取失败'
                : items.length
                  ? '选择一条运行查看详情'
                  : '暂无运行记录'
          }}
        </h2>
        <RouterLink class="secondary-button" to="/chat"
          >前往问答<AppIcon name="right" :size="15"
        /></RouterLink>
      </section>
    </div>
  </main>
</template>
