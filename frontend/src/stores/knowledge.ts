import { defineStore } from 'pinia'
import { ref } from 'vue'
import { knowledgeApi } from '../api/knowledge'
import type { KnowledgeLibrary, UploadLimits } from '../types/knowledge'

export const useKnowledge = defineStore('knowledge', () => {
  const libraries = ref<KnowledgeLibrary[]>([])
  const selectedId = ref('')
  const limits = ref<UploadLimits>({
    files: 8,
    file_bytes: 10 * 1024 ** 2,
    request_bytes: 32 * 1024 ** 2,
    extensions: ['.txt', '.md', '.pdf'],
  })
  let version = 0
  async function refresh(signal?: AbortSignal) {
    const request = ++version
    const result = await knowledgeApi.list(signal)
    if (signal?.aborted || request !== version) return
    libraries.value = result.items
    limits.value = result.limits
    // Preserve an unavailable selection: the server must reject it, never silently search project files.
  }
  return { libraries, selectedId, limits, refresh }
})
