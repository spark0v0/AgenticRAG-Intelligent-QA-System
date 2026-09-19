<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElDialog, ElMessageBox, ElSelect, ElOption } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import { useKnowledge } from '../stores/knowledge'
import { useWorkbench } from '../stores/workbench'
import { useKnowledgeDocuments } from '../composables/useKnowledgeDocuments'
import { knowledgeApi } from '../api/knowledge'
import type { KnowledgeDocument, KnowledgeMode } from '../types/knowledge'
import type { Source } from '../types'
import AppIcon from '../components/AppIcon.vue'
import KnowledgeUpload from '../components/knowledge/KnowledgeUpload.vue'
import DocumentTable from '../components/knowledge/DocumentTable.vue'
import EvidenceButton from '../components/knowledge/EvidenceButton.vue'

const store = useKnowledge()
const workbench = useWorkbench()
const router = useRouter()
const selected = ref('')
const { documents, loading, error: documentError, refresh } = useKnowledgeDocuments(selected)
const current = computed(() => store.libraries.find((item) => item.id === selected.value))
const search = ref('')
const filter = ref('all')
const filtered = computed(() =>
  documents.value.filter(
    (doc) =>
      doc.name.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()) &&
      (filter.value === 'all' || doc.status === filter.value || doc.job?.status === filter.value),
  ),
)
const busy = ref(false)
const uploading = ref(false)
const error = ref('')
const feedback = ref('')
const creating = ref(false)
const name = ref('')
const mode = ref<KnowledgeMode>('hybrid')
const probe = ref('')
const probeMode = ref<'keyword' | 'semantic' | 'hybrid'>('keyword')
const hits = ref<Source[]>([])
const probeNotice = ref('')
const probing = ref(false)
const controller = new AbortController()
let probeController: AbortController | undefined
let disposed = false
let libraryTimer: ReturnType<typeof setTimeout> | undefined
const signal = controller.signal
watch(selected, () => {
  probeController?.abort()
  hits.value = []
  probeNotice.value = ''
  search.value = ''
  filter.value = 'all'
  probeMode.value = current.value?.mode === 'hybrid' ? 'hybrid' : 'keyword'
})
async function load() {
  await store.refresh(signal)
  clearTimeout(libraryTimer)
  if (!disposed && store.libraries.some((item) => item.deleting))
    libraryTimer = setTimeout(() => void action(load), 1500)
  if (!store.libraries.some((item) => item.id === selected.value))
    selected.value = store.libraries[0]?.id || ''
}
async function action(fn: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  feedback.value = ''
  try {
    await fn()
  } catch (cause) {
    if (!disposed && cause !== 'cancel' && cause !== 'close')
      error.value = cause instanceof Error ? cause.message : '操作未完成，请重试'
  } finally {
    busy.value = false
  }
}
function create() {
  return action(async () => {
    const item = await knowledgeApi.create(name.value.trim(), mode.value, signal)
    await load()
    selected.value = item.id
    creating.value = false
    name.value = ''
    feedback.value = '知识库已创建，现在可以上传资料。'
  })
}
function rename() {
  const item = current.value
  if (!item) return
  void action(async () => {
    const value = await ElMessageBox.prompt('为知识库设置一个清楚易识别的名称', '重命名知识库', {
      inputValue: item.name,
      inputValidator: (v: string) =>
        (!!v?.trim() && v.trim().length <= 80) || '请输入 1～80 个字符',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    await knowledgeApi.rename(item.id, value.value.trim(), signal)
    await load()
  })
}
function remove() {
  const item = current.value
  if (!item) return
  void action(async () => {
    await ElMessageBox.confirm(
      `删除“${item.name}”中的原文和检索索引。历史回答仍保留证据快照。`,
      '删除知识库',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '保留' },
    )
    const result = await knowledgeApi.remove(item.id, signal)
    feedback.value = result.message || '知识库已删除'
    await load()
    await refresh()
  })
}
function upload(files: File[]) {
  const key = selected.value
  void action(async () => {
    uploading.value = true
    try {
      const result = await knowledgeApi.upload(key, files, signal)
      const duplicates = result.items.filter((item) => item.duplicate).length
      feedback.value = `${result.items.length - duplicates} 个文档已进入索引队列${duplicates ? `，${duplicates} 个重复文件已跳过` : ''}。`
      await load()
      if (key === selected.value) await refresh()
    } finally {
      uploading.value = false
    }
  })
}
function documentAction(doc: KnowledgeDocument, kind: 'retry' | 'cancel' | 'delete') {
  void action(async () => {
    if (kind === 'delete')
      await ElMessageBox.confirm(
        `删除“${doc.name}”的原文和索引？历史证据快照将保留。`,
        '删除文档',
        { confirmButtonText: '删除', cancelButtonText: '保留', type: 'warning' },
      )
    await knowledgeApi.documentAction(doc.kb_id, doc.id, kind, signal)
    if (selected.value === doc.kb_id) await refresh()
    await load()
  })
}
async function runProbe() {
  if (!probe.value.trim() || !selected.value) return
  probeController?.abort()
  const request = new AbortController()
  probeController = request
  probing.value = true
  hits.value = []
  probeNotice.value = ''
  try {
    const result = await knowledgeApi.search(
      selected.value,
      probe.value,
      probeMode.value,
      request.signal,
    )
    if (request.signal.aborted) return
    hits.value = result.documents.map((doc, index) => ({
      ...doc.metadata,
      citation_id: `S${index + 1}`,
      source: doc.source,
      excerpt: doc.content,
    }))
    const states: Record<string, string> = {
      empty: '知识库为空，请先上传资料。',
      indexing: '文档仍在索引，请稍后再试。',
      not_ready: '文档尚未就绪，请检查失败状态或重建索引。',
      no_match: '没有检索到匹配的片段，请换一种问法。',
      ready: `找到 ${hits.value.length} 个证据片段。`,
    }
    probeNotice.value = states[result.metadata.state] || result.metadata.state
  } catch (cause) {
    if (!request.signal.aborted)
      probeNotice.value = cause instanceof Error ? cause.message : '检索服务错误'
  } finally {
    if (probeController === request) probing.value = false
  }
}
function ask() {
  store.selectedId = selected.value
  workbench.searchScope = 'local'
  workbench.thinking = 'retrieval'
  void router.push('/chat')
}
onMounted(() => void action(load))
onBeforeUnmount(() => {
  disposed = true
  controller.abort()
  probeController?.abort()
  clearTimeout(libraryTimer)
})
</script>
<template>
  <main class="kb-page">
    <header class="kb-page-heading">
      <div>
        <span class="kb-eyebrow">你的资料，回答的依据</span>
        <h1>知识库</h1>
        <p>整理本地文档，在问答中追溯每一份证据。</p>
      </div>
      <button class="kb-primary" :disabled="busy" @click="creating = true">
        <AppIcon name="plus" :size="17" />创建知识库
      </button>
    </header>
    <p v-if="error" role="alert" class="kb-error">
      {{ error }} <button :disabled="busy" @click="action(load)">重新加载</button>
    </p>
    <p v-if="feedback" role="status" class="kb-feedback">{{ feedback }}</p>
    <div class="kb-layout">
      <aside class="kb-libraries" aria-label="知识库列表">
        <span class="kb-section-label">全部知识库 · {{ store.libraries.length }}</span>
        <button
          v-for="item in store.libraries"
          :key="item.id"
          :class="{ selected: selected === item.id }"
          :aria-pressed="selected === item.id"
          @click="selected = item.id"
        >
          <AppIcon name="book" :size="19" /><span
            ><strong>{{ item.name }}</strong
            ><small
              >{{ item.document_count }} 个文档 ·
              {{ item.mode === 'hybrid' ? '语义 + 关键词' : '关键词' }}</small
            ></span
          >
        </button>
        <p v-if="!store.libraries.length" class="muted">
          {{ busy ? '正在读取…' : '还没有知识库' }}
        </p>
      </aside>
      <section v-if="current" class="kb-content" :aria-label="current.name">
        <header class="kb-library-heading">
          <div>
            <h2>{{ current.name }}</h2>
            <p>
              {{ documents.filter((doc) => doc.status === 'completed').length }} 个文档可检索 ·
              {{ current.mode === 'hybrid' ? 'BGE 中文语义 + BM25 融合' : 'BM25 关键词检索' }}
            </p>
          </div>
          <div class="kb-row-actions">
            <button :disabled="busy" @click="rename">重命名</button
            ><button class="kb-danger" :disabled="busy" @click="remove">删除知识库</button
            ><button class="kb-primary" :disabled="!!current.deleting" @click="ask">
              基于资料提问<AppIcon name="right" :size="15" />
            </button>
          </div>
        </header>
        <KnowledgeUpload
          :limits="store.limits"
          :busy="busy || uploading || !!current.deleting"
          @upload="upload"
        />
        <div class="kb-filter">
          <label class="kb-search"
            ><AppIcon name="search" :size="17" /><input
              v-model="search"
              placeholder="搜索文档名称"
              aria-label="搜索文档名称" /></label
          ><ElSelect v-model="filter" aria-label="筛选索引状态"
            ><ElOption label="所有状态" value="all" /><ElOption
              label="可检索"
              value="completed" /><ElOption label="等待索引" value="queued" /><ElOption
              label="索引中"
              value="indexing" /><ElOption label="解析中" value="parsing" /><ElOption
              label="切分中"
              value="splitting" /><ElOption label="索引失败" value="failed" /><ElOption
              label="已取消"
              value="cancelled" /><ElOption label="清理失败" value="delete_failed" /></ElSelect
          ><button aria-label="刷新文档列表" @click="refresh()">
            <AppIcon name="refresh" :size="17" />
          </button>
        </div>
        <p v-if="documentError" role="alert" class="kb-error">
          {{ documentError }} <button @click="refresh()">重试</button>
        </p>
        <p v-if="loading" role="status" class="muted">正在读取文档…</p>
        <DocumentTable
          v-else-if="filtered.length"
          :documents="filtered"
          :busy="busy"
          @action="documentAction"
        />
        <div v-else class="kb-empty">
          <AppIcon name="book" :size="30" />
          <h3>{{ documents.length ? '没有匹配的文档' : '从第一份资料开始' }}</h3>
          <p>
            {{
              documents.length
                ? '尝试其他关键词或状态。'
                : '上传后可查看索引状态，并在提问时选择此知识库。'
            }}
          </p>
        </div>
        <details class="kb-probe">
          <summary>检索预览 <span>直接查看命中片段，不调用回答模型</span></summary>
          <form @submit.prevent="runProbe">
            <label for="kb-probe">用一个问题检查资料是否能被找到</label>
            <div class="kb-probe-controls">
              <input
                id="kb-probe"
                v-model="probe"
                maxlength="2000"
                placeholder="例如：项目的报销审批流程是什么？"
              /><ElSelect v-model="probeMode" aria-label="检索模式"
                ><ElOption label="关键词" value="keyword" /><ElOption
                  v-if="current.mode === 'hybrid'"
                  label="语义"
                  value="semantic" /><ElOption
                  v-if="current.mode === 'hybrid'"
                  label="融合"
                  value="hybrid" /></ElSelect
              ><button class="kb-primary" :disabled="probing || !probe.trim()">
                {{ probing ? '检索中…' : '检索' }}
              </button>
            </div>
          </form>
          <p v-if="probeNotice" role="status">{{ probeNotice }}</p>
          <article v-for="hit in hits" :key="hit.chunk_id" class="kb-hit">
            <strong>{{ hit.source }}</strong>
            <p>{{ hit.excerpt }}</p>
            <EvidenceButton :source="hit" />
          </article>
        </details>
      </section>
      <section v-else class="kb-empty kb-first">
        <AppIcon name="book" :size="42" />
        <h2>让资料成为可追溯的答案</h2>
        <p>
          为一个项目或主题创建知识库。上传的文档独立检索，<br />不会与其他知识库或项目源码混合。
        </p>
        <button class="kb-primary" @click="creating = true">创建第一个知识库</button>
      </section>
    </div>
    <ElDialog
      v-model="creating"
      title="创建知识库"
      width="min(500px, 94vw)"
      :close-on-click-modal="!busy"
    >
      <form id="kb-create" class="kb-create" @submit.prevent="create">
        <label for="kb-name">知识库名称</label
        ><input
          id="kb-name"
          v-model="name"
          required
          maxlength="80"
          placeholder="例如：产品手册、面试笔记"
          autofocus
        /><label for="kb-mode">检索方式</label
        ><ElSelect id="kb-mode" v-model="mode" aria-label="检索方式"
          ><ElOption label="中文语义 + 关键词融合" value="hybrid" /><ElOption
            label="仅关键词（无需模型）"
            value="keyword"
        /></ElSelect>
        <p class="notice">
          {{
            mode === 'hybrid'
              ? '使用本机 CPU 运行 BGE 中文小模型。首次使用须按启动文档下载约 90 MB 模型；未就绪时索引会明确失败，可准备模型后重试。'
              : '使用中文二元分词与 BM25，不具备语义理解能力。适合无需模型的基础文档检索。'
          }}
        </p>
      </form>
      <template #footer
        ><button :disabled="busy" @click="creating = false">取消</button
        ><button class="kb-primary" form="kb-create" :disabled="busy || !name.trim()">
          {{ busy ? '创建中…' : '创建知识库' }}
        </button></template
      >
    </ElDialog>
  </main>
</template>
