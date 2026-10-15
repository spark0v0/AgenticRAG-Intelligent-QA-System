import type { Conversation } from '../types/chat'

type Draft = Pick<
  Conversation,
  'id' | 'draft' | 'knowledgeBaseId' | 'searchScope' | 'modelProfile' | 'thinkingMode'
> & { savedAt: number }
const key = 'rag-text-drafts-v1'
export function createDraftStorage() {
  const entries = new Map<string, Draft>()
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) || '[]')
    if (Array.isArray(value))
      for (const item of value) {
        if (
          !item ||
          typeof item.id !== 'string' ||
          typeof item.draft !== 'string' ||
          typeof item.savedAt !== 'number' ||
          Date.now() - item.savedAt > 30 * 86400000
        )
          continue
        entries.set(item.id, {
          id: item.id,
          draft: item.draft.slice(0, 50000),
          savedAt: item.savedAt,
          knowledgeBaseId: typeof item.knowledgeBaseId === 'string' ? item.knowledgeBaseId : '',
          modelProfile: typeof item.modelProfile === 'string' ? item.modelProfile : undefined,
          thinkingMode: ['', 'quick', 'retrieval', 'deep'].includes(item.thinkingMode)
            ? item.thinkingMode
            : '',
          searchScope: ['auto', 'local', 'web', 'all'].includes(item.searchScope)
            ? item.searchScope
            : 'auto',
        })
      }
  } catch {
    /* Optional browser storage. */
  }
  function flush() {
    clearTimeout(timer)
    try {
      localStorage.setItem(
        key,
        JSON.stringify([...entries.values()].sort((a, b) => b.savedAt - a.savedAt).slice(0, 20)),
      )
    } catch {
      /* History remains on the server. */
    }
  }
  function save(conversation: Conversation) {
    const { id, draft, knowledgeBaseId, searchScope, modelProfile, thinkingMode } = conversation
    if (draft)
      entries.set(id, {
        id,
        draft: draft.slice(0, 50000),
        knowledgeBaseId,
        searchScope,
        modelProfile,
        thinkingMode,
        savedAt: Date.now(),
      })
    else if (!entries.delete(id)) return
    clearTimeout(timer)
    timer = setTimeout(flush, 250)
  }
  return {
    save,
    flush,
    get: (id: string) => entries.get(id),
    remove(id: string) {
      entries.delete(id)
      flush()
    },
  }
}
