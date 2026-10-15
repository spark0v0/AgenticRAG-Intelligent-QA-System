<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElSelect, ElOption } from 'element-plus'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import { knowledgeApi } from '../../api/knowledge'
import type { Source } from '../../types'
import type {
  KnowledgeLibrary,
  RetrievalComparison,
  RetrievalDocument,
  RetrievalMode,
  RetrievalResult,
} from '../../types/knowledge'
import EvidenceButton from './EvidenceButton.vue'

const props = defineProps<{ library: KnowledgeLibrary }>()
const query = ref('')
const queryInput = ref<HTMLInputElement>()
const mode = ref<RetrievalMode | 'compare'>('keyword')
const busy = ref(false)
const error = ref('')
const feedback = ref('')
const results = ref<RetrievalResult[]>([])
const comparison = ref<RetrievalComparison>()
const submitted = ref<{ query: string; library: string }>()
let controller: AbortController | undefined
const labels: Record<RetrievalMode, string> = {
  keyword: '关键词',
  semantic: '语义',
  hybrid: '融合',
}
const methods: Record<RetrievalMode, string> = {
  keyword: 'BM25',
  semantic: 'BGE / Chroma',
  hybrid: 'RRF',
}
const states = {
  empty: '知识库为空，请先上传资料。',
  indexing: '文档仍在索引，请稍后再试。',
  not_ready: '文档尚未就绪，请检查失败状态或重建索引。',
  no_match: '没有找到匹配片段，可尝试更具体的关键词。',
  unavailable: '此模式暂不可用。',
  error: '检索服务暂不可用，请稍后重试。',
  ready: '',
}
const groups = computed(() => {
  // The same chunk keeps one preview number across columns; these are not answer citations.
  const ids = [
    ...new Set(
      results.value.flatMap((result) => result.documents.map((doc) => doc.metadata.chunk_id)),
    ),
  ].sort()
  return results.value.map((result) => ({
    ...result,
    hits: result.documents.map((doc, index) => {
      const fragment = ids.indexOf(doc.metadata.chunk_id) + 1
      const source: Source = {
        ...doc.metadata,
        citation_id: `S${fragment}`,
        source: doc.source,
        excerpt: doc.content,
      }
      return { doc, source, fragment, rank: index + 1 }
    }),
  }))
})
const overlap = computed(() => {
  if (!comparison.value) return null
  const [keyword, semantic] = comparison.value.results
  if (
    !keyword ||
    !semantic ||
    ![keyword, semantic].every((result) => ['ready', 'no_match'].includes(result.metadata.state))
  )
    return null
  const ids = new Set(keyword.documents.map((doc) => doc.metadata.chunk_id))
  return semantic.documents.filter((doc) => ids.has(doc.metadata.chunk_id)).length
})
const semanticAvailable = computed(() =>
  comparison.value?.results.some(
    (result) =>
      result.metadata.mode === 'semantic' && ['ready', 'no_match'].includes(result.metadata.state),
  ),
)
const durations = computed(() =>
  comparison.value
    ? [
        { label: '候选读取', value: comparison.value.timings.snapshot_ms },
        { label: '关键词计算', value: comparison.value.timings.keyword_ms },
        { label: '查询嵌入与向量检索', value: comparison.value.timings.semantic_ms },
        { label: '融合排序', value: comparison.value.timings.fusion_ms },
      ]
    : [],
)
function duration(value: number) {
  return `${value < 1 ? '< 1' : value.toFixed(1)} ms`
}
function score(doc: RetrievalDocument, selectedMode: RetrievalMode) {
  if (!doc.ranking) return ''
  const value =
    selectedMode === 'keyword'
      ? doc.ranking.bm25_score
      : selectedMode === 'semantic'
        ? doc.ranking.cosine_similarity
        : doc.ranking.rrf_score
  const label =
    selectedMode === 'keyword' ? 'BM25' : selectedMode === 'semantic' ? '余弦相似度' : 'RRF'
  return value === null ? '' : `${label} ${value.toFixed(selectedMode === 'hybrid' ? 5 : 3)}`
}
function abort() {
  controller?.abort()
  controller = undefined
  busy.value = false
}
function stopWaiting() {
  abort()
  feedback.value = '已停止等待；服务端已开始的本地检索可能继续完成。'
  void nextTick(() => queryInput.value?.focus())
}
watch(
  () => props.library.id,
  () => {
    abort()
    query.value = ''
    mode.value = props.library.mode === 'hybrid' ? 'hybrid' : 'keyword'
    results.value = []
    comparison.value = undefined
    submitted.value = undefined
    error.value = ''
    feedback.value = ''
  },
  { immediate: true, flush: 'sync' },
)
async function search() {
  if (busy.value || !query.value.trim()) return
  const request = new AbortController()
  controller = request
  const libraryId = props.library.id
  const question = query.value.trim()
  const selectedMode = mode.value
  busy.value = true
  error.value = ''
  feedback.value = ''
  results.value = []
  comparison.value = undefined
  submitted.value = { query: question, library: props.library.name }
  try {
    if (selectedMode === 'compare') {
      const response = await knowledgeApi.compare(libraryId, question, request.signal)
      if (request.signal.aborted || controller !== request || props.library.id !== libraryId) return
      comparison.value = response
      results.value = response.results
    } else {
      const response = await knowledgeApi.search(libraryId, question, selectedMode, request.signal)
      if (request.signal.aborted || controller !== request || props.library.id !== libraryId) return
      results.value = [response]
    }
    feedback.value =
      selectedMode === 'compare'
        ? '检索结果已返回，请查看各模式状态。'
        : `检索完成，找到 ${results.value[0]?.documents.length ?? 0} 个片段。`
  } catch (cause) {
    if (!request.signal.aborted && controller === request)
      error.value = cause instanceof Error ? cause.message : '检索失败，请重试。'
  } finally {
    if (controller === request) {
      busy.value = false
      controller = undefined
    }
  }
}
onBeforeUnmount(abort)
</script>

<template>
  <details class="kb-probe">
    <summary>检索预览 <span>查看命中片段与排名，不调用回答模型</span></summary>
    <form @submit.prevent="search">
      <label for="kb-probe">用一个问题检查资料是否能被找到</label>
      <div class="kb-probe-controls">
        <input
          id="kb-probe"
          ref="queryInput"
          v-model="query"
          maxlength="2000"
          placeholder="例如：差旅报销需要哪些材料？"
        />
        <ElSelect v-model="mode" aria-label="检索模式">
          <ElOption label="关键词" value="keyword" />
          <ElOption v-if="library.mode === 'hybrid'" label="语义" value="semantic" />
          <ElOption v-if="library.mode === 'hybrid'" label="融合" value="hybrid" />
          <ElOption label="三种模式对比" value="compare" />
        </ElSelect>
        <button class="kb-primary" :disabled="busy || !query.trim()">
          {{ busy ? '检索中…' : mode === 'compare' ? '开始对比' : '检索' }}
        </button>
        <button v-if="busy" type="button" @click="stopWaiting">停止等待</button>
      </div>
    </form>
    <p v-if="error" role="alert" class="kb-probe-error">{{ error }}</p>
    <p role="status" class="kb-probe-feedback">
      {{ busy ? '正在读取当前知识库的有效索引…' : feedback }}
    </p>
    <div v-if="results.length && submitted" class="kb-probe-results">
      <div class="kb-probe-result-heading">
        <div>
          <strong>{{ submitted.query }}</strong
          ><small
            >{{ submitted.library }} · {{ results[0]?.metadata.candidate_count }} 个候选片段</small
          >
        </div>
        <span v-if="comparison">服务端 {{ duration(comparison.timings.total_ms) }}</span>
      </div>
      <p v-if="overlap !== null" class="kb-probe-note">
        关键词与语义前 {{ comparison?.limit }} 条结果共有
        {{ overlap }} 个片段，相同编号表示同一片段。
      </p>
      <div class="kb-probe-grid" :class="{ comparing: comparison }">
        <section
          v-for="group in groups"
          :key="group.metadata.mode"
          class="kb-probe-column"
          :aria-label="`${labels[group.metadata.mode]}检索结果`"
        >
          <header>
            <h3>
              {{ labels[group.metadata.mode] }} <small>{{ methods[group.metadata.mode] }}</small>
            </h3>
            <span v-if="group.metadata.state === 'unavailable'">未启用</span>
            <span v-else-if="group.metadata.state === 'error'" class="kb-probe-error"
              >检索失败</span
            >
            <span v-else-if="group.metadata.state === 'indexing'">索引中</span>
            <span v-else-if="group.metadata.state === 'not_ready'">未就绪</span>
            <span v-else>{{ group.hits.length }} 条</span>
          </header>
          <p
            v-if="group.metadata.state !== 'ready'"
            class="kb-probe-empty"
            :class="{ failed: group.metadata.state === 'error' }"
          >
            {{ group.metadata.reason || states[group.metadata.state] }}
          </p>
          <ol v-else>
            <li v-for="hit in group.hits" :key="hit.source.chunk_id" class="kb-hit">
              <div class="kb-hit-ranking">
                <span>#{{ hit.rank }}</span
                ><span v-if="comparison">片段 {{ hit.fragment }}</span
                ><small v-if="comparison">{{ score(hit.doc, group.metadata.mode) }}</small>
              </div>
              <strong>{{ hit.source.source }}</strong>
              <p>{{ hit.source.excerpt }}</p>
              <small v-if="comparison && hit.doc.ranking" class="kb-hit-positions"
                >关键词
                {{ hit.doc.ranking.keyword_rank ? `#${hit.doc.ranking.keyword_rank}` : '未入选' }} ·
                语义
                {{
                  !semanticAvailable
                    ? '不可用'
                    : hit.doc.ranking.semantic_rank
                      ? `#${hit.doc.ranking.semantic_rank}`
                      : '未入选'
                }}</small
              >
              <EvidenceButton :source="hit.source" />
            </li>
          </ol>
        </section>
      </div>
      <details v-if="comparison" class="kb-probe-metrics">
        <summary>耗时与分数说明</summary>
        <dl>
          <template v-for="item in durations" :key="item.label"
            ><dt>{{ item.label }}</dt>
            <dd>{{ item.value === null ? '未执行' : duration(item.value) }}</dd></template
          >
        </dl>
        <p>
          三种模式共用候选片段和一次查询嵌入。以上为本次服务端各阶段耗时，不包含网络与页面渲染，不能视作三次独立请求的性能对比。
        </p>
        <p>
          BM25、余弦相似度和 RRF 的量纲不同，只用于各自模式的排序，不代表回答准确率。每路最多取 50
          个候选，语义相似度阈值为 0.35，RRF 参数 k = 60。
        </p>
      </details>
    </div>
  </details>
</template>
