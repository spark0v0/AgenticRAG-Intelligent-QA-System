<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { ElDrawer } from 'element-plus'
import 'element-plus/es/components/drawer/style/css'
import { knowledgeApi } from '../../api/knowledge'
import type { Source } from '../../types'
import type { Evidence } from '../../types/knowledge'
const props = defineProps<{ source: Source }>()
const open = ref(false)
const loading = ref(false)
const error = ref('')
const evidence = ref<Evidence>()
let controller: AbortController | undefined
async function show() {
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  open.value = true
  loading.value = true
  evidence.value = undefined
  error.value = ''
  try {
    const result = await knowledgeApi.evidence(props.source, signal)
    if (!signal.aborted) evidence.value = result
  } catch (cause) {
    if (!signal.aborted) error.value = cause instanceof Error ? cause.message : '证据加载失败'
  } finally {
    if (!signal.aborted) loading.value = false
  }
}
function close() {
  controller?.abort()
  loading.value = false
}
watch(
  () => props.source,
  () => {
    close()
    open.value = false
  },
)
onBeforeUnmount(close)
</script>
<template>
  <template v-if="source.document_id && source.knowledge_base_id && source.chunk_id">
    <small class="kb-source-location"
      >本地文档<span v-if="source.page"> · 第 {{ source.page }} 页</span
      ><span v-if="source.heading"> · {{ source.heading }}</span></small
    >
    <button class="kb-evidence-button" @click="show">查看证据与原文</button>
    <ElDrawer
      v-model="open"
      title="文档证据"
      size="min(600px, 100vw)"
      append-to-body
      @close="close"
    >
      <div class="kb-evidence">
        <h2>{{ source.document_name || source.source }}</h2>
        <p class="muted">
          文档版本 {{ source.version?.slice(0, 12)
          }}<span v-if="source.page"> · 第 {{ source.page }} 页</span
          ><span v-if="source.heading"> · {{ source.heading }}</span>
        </p>
        <h3>回答采用的证据快照</h3>
        <blockquote>{{ source.excerpt || '这条记录没有保存证据片段。' }}</blockquote>
        <p v-if="loading" role="status">正在检查原文…</p>
        <p v-else-if="error" class="kb-error" role="alert">
          {{ error }} <button @click="show">重试</button>
        </p>
        <template v-else-if="evidence">
          <p
            v-if="!evidence.original_available || evidence.version !== source.version"
            class="notice"
          >
            原文已删除、版本变化或不可用。上方快照仍保留回答时的证据。
          </p>
          <template v-else>
            <h3>原文位置的完整片段</h3>
            <p v-if="evidence.position" class="muted">
              {{ evidence.position.page ? `第 ${evidence.position.page} 页 · ` : '' }}字符
              {{ evidence.position.start + 1 }}—{{ evidence.position.end }}（{{
                evidence.position.page ? '页内提取文字' : 'UTF-8 正文'
              }}）
            </p>
            <pre>{{ evidence.content || '索引版本已改变，请打开原文核对上方证据快照。' }}</pre>
            <a
              class="kb-evidence-button"
              :href="knowledgeApi.original(source) + (source.page ? `#page=${source.page}` : '')"
              target="_blank"
              rel="noopener noreferrer"
              >打开原始文档{{ source.page ? `第 ${source.page} 页` : '' }}</a
            >
          </template>
        </template>
        <small class="muted">引用表示模型使用了这些检索资料，不代表每句话已经完成事实核验。</small>
      </div>
    </ElDrawer>
  </template>
</template>
