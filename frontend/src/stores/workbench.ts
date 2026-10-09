import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import { useKnowledge } from './knowledge'
import { readEvents } from '../api/sse'
import { ActiveRun } from '../chat/activeRun'
import { restoreConversation } from '../chat/history'
import type { Conversation } from '../types/chat'
import type { QueryRequest, SessionSummary, SystemStatus } from '../types'

const storage = {
  get(key: string) {
    try {
      return localStorage.getItem(key)
    } catch {
      return null
    }
  },
  set(key: string, value: string) {
    try {
      localStorage.setItem(key, value)
    } catch {
      /* Private-mode storage is optional. */
    }
  },
  remove(key: string) {
    try {
      localStorage.removeItem(key)
    } catch {
      /* Storage is optional. */
    }
  },
}

export const useWorkbench = defineStore('workbench', () => {
  // Migrate only the former live pointer; retired sample history stays isolated.
  if (!storage.get('rag-session') && storage.get('rag-session-live'))
    storage.set('rag-session', storage.get('rag-session-live')!)
  for (const key of ['rag-mode', 'rag-session-demo', 'rag-session-live']) storage.remove(key)
  const system = ref<SystemStatus>()
  const sessions = ref<SessionSummary[]>([])
  const conversations = ref<Record<string, Conversation>>({})
  const currentId = ref('')
  const selectedRun = ref('')
  const model = ref(storage.get('rag-model') || '')
  const savedThinking = storage.get('rag-thinking') || ''
  const thinking = ref(
    ['', 'quick', 'retrieval', 'deep'].includes(savedThinking) ? savedThinking : '',
  )
  const loading = ref(false)
  const searchScope = ref<'auto' | 'local' | 'web' | 'all'>('auto')
  const loadingSession = ref(false)
  const error = ref('')
  const theme = ref(storage.get('rag-theme') || 'light')
  const pending = new Map<string, ActiveRun>() // non-serializable resources stay outside Pinia state
  let loadVersion = 0
  let sessionController: AbortController | undefined
  let initVersion = 0
  let sessionsVersion = 0
  let restoring = false
  watch(
    model,
    (value) => {
      storage.set('rag-model', value)
      if (!restoring && current.value) current.value.modelProfile = value
    },
    { flush: 'sync' },
  )
  watch(
    thinking,
    (value) => {
      storage.set('rag-thinking', value)
      if (!restoring && current.value) current.value.thinkingMode = value
    },
    { flush: 'sync' },
  )
  const current = computed(() => conversations.value[currentId.value])
  const knowledge = useKnowledge()
  watch(
    currentId,
    () => {
      const conversation = current.value
      const scope = conversation?.searchScope || (conversation?.knowledgeBaseId ? 'local' : 'auto')
      restoring = true
      knowledge.selectedId = conversation?.knowledgeBaseId || ''
      searchScope.value = scope
      model.value = conversation?.modelProfile ?? model.value
      thinking.value = conversation?.thinkingMode ?? thinking.value
      restoring = false
    },
    { flush: 'sync' },
  )
  watch(
    () => knowledge.selectedId,
    (id) => {
      if (restoring) return
      if (current.value) current.value.knowledgeBaseId = id
      if (id) {
        if (searchScope.value !== 'all') searchScope.value = 'local'
        if (thinking.value === 'quick') thinking.value = 'retrieval'
      }
    },
    { flush: 'sync' },
  )
  watch(
    searchScope,
    (scope) => {
      if (!restoring && current.value) current.value.searchScope = scope
    },
    { flush: 'sync' },
  )
  const busy = computed(() => !!current.value?.activeRun)
  const hasPending = computed(() => Object.values(conversations.value).some((c) => !!c.activeRun))
  const profile = computed(() => system.value?.model_profiles.find((p) => p.id === model.value))
  const selectedMessage = computed(() =>
    current.value?.messages.findLast(
      (m) => m.role === 'assistant' && (!selectedRun.value || m.run_id === selectedRun.value),
    ),
  )
  const selectedEvents = computed(
    () =>
      current.value?.events.filter(
        (e) => e.run_id === (selectedRun.value || selectedMessage.value?.run_id),
      ) ?? [],
  )

  function remember() {
    storage.set('rag-session', currentId.value)
  }
  function newChat(persist = true) {
    loadVersion++
    sessionController?.abort()
    loadingSession.value = false
    const id = crypto.randomUUID()
    conversations.value[id] = {
      id,
      title: '新会话',
      knowledgeBaseId: knowledge.selectedId,
      searchScope: searchScope.value,
      modelProfile: model.value,
      thinkingMode: thinking.value,
      messages: [],
      events: [],
      status: 'idle',
      draft: '',
      images: [],
    }
    currentId.value = id
    selectedRun.value = ''
    if (persist) remember()
  }
  async function refreshSessions() {
    const version = ++sessionsVersion
    const response = await api.sessions()
    if (version !== sessionsVersion) return
    const active = sessions.value.filter(
      (s) =>
        conversations.value[s.session_id]?.activeRun &&
        !response.items.some((item) => item.session_id === s.session_id),
    )
    sessions.value = [...active, ...response.items]
  }
  async function loadSession(id: string) {
    const version = ++loadVersion
    sessionController?.abort()
    selectedRun.value = ''
    if (conversations.value[id]) {
      currentId.value = id
      loadingSession.value = false
      remember()
      return
    }
    sessionController = new AbortController()
    loadingSession.value = true
    error.value = ''
    try {
      const detail = await api.session(id, sessionController.signal)
      if (version !== loadVersion) return
      conversations.value[id] = restoreConversation(detail)
      const messages = conversations.value[id]!.messages
      currentId.value = id
      selectedRun.value = messages.findLast((m) => m.role === 'assistant')?.run_id ?? ''
      remember()
    } catch (e) {
      if (version === loadVersion && !(e instanceof DOMException && e.name === 'AbortError'))
        error.value = messageOf(e)
    } finally {
      if (version === loadVersion) loadingSession.value = false
    }
  }
  async function initialize() {
    const version = ++initVersion
    loading.value = true
    error.value = ''
    try {
      const status = await api.status()
      if (version !== initVersion) return
      system.value = status
      if (
        !status.model_profiles.some((p) => p.id === model.value) ||
        (model.value === 'default' &&
          !status.model_profiles.find((p) => p.id === 'default')?.configured)
      ) {
        const defaultProfile = status.model_profiles.find(
          (p) => p.id === status.default_model_profile,
        )
        model.value =
          (defaultProfile?.configured
            ? defaultProfile.id
            : status.model_profiles.find((p) => p.configured)?.id) || status.default_model_profile
      }
      await refreshSessions()
      if (version !== initVersion) return
      if (!currentId.value) {
        const saved = storage.get('rag-session')
        if (saved && sessions.value.some((s) => s.session_id === saved)) await loadSession(saved)
        else newChat()
      }
    } catch (e) {
      if (version === initVersion) error.value = messageOf(e)
    } finally {
      if (version === initVersion) {
        loading.value = false
        if (!currentId.value) newChat(false)
      }
    }
  }
  function toggleTheme() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
    storage.set('rag-theme', theme.value)
  }
  async function send(text?: string) {
    const conversation = current.value
    if (!conversation || conversation.activeRun || !system.value || loadingSession.value) return
    if (!profile.value?.configured) {
      conversation.error = '所选模型尚未配置，请检查后端模型档案。'
      return
    }
    const query = (text ?? conversation.draft).trim()
    if (!query && !conversation.images.length) return
    if (conversation.images.length && !profile.value?.supports_vision) {
      conversation.error = '当前模型不支持图片，请移除附件或切换模型。'
      return
    }
    const id = crypto.randomUUID()
    const payload: QueryRequest = {
      query,
      session_id: conversation.id,
      run_id: id,
      model_profile: model.value,
      images: [...conversation.images],
      context: {
        thinking_mode: thinking.value,
        search_scope: searchScope.value,
        knowledge_base_id: useKnowledge().selectedId || undefined,
      },
    }
    conversation.activeRun = id
    conversation.status = 'submitting'
    conversation.error = ''
    conversation.restoreNotice = undefined
    conversation.title = query.slice(0, 24) || '图片问答'
    conversation.draft = ''
    conversation.images = []
    const timestamp = Date.now() / 1000
    conversation.messages.push({
      id: `${id}-user`,
      run_id: id,
      role: 'user',
      content: query,
      timestamp,
      attachments: payload.images,
    })
    conversation.messages.push({
      id: `${id}-assistant`,
      run_id: id,
      role: 'assistant',
      content: '',
      timestamp,
      status: 'submitting',
    })
    const assistant = conversation.messages[conversation.messages.length - 1]!
    const run = new ActiveRun(payload, conversation, assistant)
    pending.set(id, run)
    selectedRun.value = id
    if (!sessions.value.some((s) => s.session_id === conversation.id))
      sessions.value.unshift({
        session_id: conversation.id,
        session_title: conversation.title,
        preview: query,
        turn_count: 0,
        updated_at: timestamp,
      })
    try {
      const response = await api.stream(payload, run.controller.signal)
      await readEvents(response, run.receive, { run_id: id, session_id: conversation.id })
    } catch (e) {
      run.fail(e)
    } finally {
      run.release()
      if (pending.get(id) === run) pending.delete(id)
      await refreshSessions().catch(() => {
        if (!conversation.activeRun && conversation.messages.at(-1) === assistant)
          conversation.error = '会话列表暂未刷新，回答已保留。'
      })
    }
  }
  async function cancel() {
    const id = current.value?.activeRun
    const run = id ? pending.get(id) : undefined
    if (!id || !run || run.cancelling) return
    run.cancelling = true
    try {
      const response = await api.cancel(id)
      // Completion can win the race against cancellation; the committed server result wins.
      if (response.run?.status === 'success' && response.run.result) {
        run.complete(response.run.result, '本轮已在取消前完成。')
      }
      if (pending.get(id) === run) run.abort()
    } catch {
      if (current.value?.activeRun === id)
        current.value.error = '取消确认失败，已断开连接。服务端将在检测断开后停止，请刷新核对。'
      run.abort()
    }
  }
  function dispose() {
    initVersion++
    sessionsVersion++
    loadVersion++
    sessionController?.abort()
    for (const [id, run] of pending) {
      void api.cancel(id).catch(() => undefined)
      run.abort()
    }
  }
  return {
    system,
    sessions,
    conversations,
    currentId,
    current,
    selectedRun,
    selectedMessage,
    selectedEvents,
    model,
    thinking,
    searchScope,
    loading,
    loadingSession,
    error,
    theme,
    busy,
    hasPending,
    profile,
    initialize,
    refreshSessions,
    loadSession,
    newChat,
    send,
    cancel,
    toggleTheme,
    dispose,
  }
})

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : '请求失败，请稍后重试。'
}
