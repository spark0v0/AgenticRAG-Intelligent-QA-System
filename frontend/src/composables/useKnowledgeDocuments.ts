import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { knowledgeApi } from '../api/knowledge'
import { activeIndex, type KnowledgeDocument } from '../types/knowledge'

export function useKnowledgeDocuments(id: Ref<string>) {
  const documents = ref<KnowledgeDocument[]>([])
  const loading = ref(false)
  const error = ref('')
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let version = 0
  let disposed = false
  async function refresh(quiet = false) {
    clearTimeout(timer)
    controller?.abort()
    controller = new AbortController()
    const signal = controller.signal
    const request = ++version
    const key = id.value
    if (!key) {
      documents.value = []
      loading.value = false
      return
    }
    if (!quiet) loading.value = true
    try {
      const result = await knowledgeApi.documents(key, signal)
      if (disposed || request !== version) return
      documents.value = result.items
      error.value = ''
      if (result.items.some((doc) => activeIndex(doc.status) || activeIndex(doc.job?.status)))
        timer = setTimeout(() => void refresh(true), 1500)
    } catch (cause) {
      if (!signal.aborted && !disposed && request === version)
        error.value = cause instanceof Error ? cause.message : '文档加载失败'
    } finally {
      if (request === version) loading.value = false
    }
  }
  watch(
    id,
    () => {
      documents.value = []
      error.value = ''
      void refresh()
    },
    { immediate: true },
  )
  onBeforeUnmount(() => {
    disposed = true
    ++version
    controller?.abort()
    clearTimeout(timer)
  })
  return { documents, loading, error, refresh }
}
