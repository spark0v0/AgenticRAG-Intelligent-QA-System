import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import { readEvents } from '../api/sse'
import type {
  ExecutionEvent,
  ImageAttachment,
  Message,
  QueryRequest,
  RunStatus,
  SessionSummary,
  SystemStatus,
} from '../types'

interface Conversation {
  id: string
  title: string
  messages: Message[]
  events: ExecutionEvent[]
  status: RunStatus
  activeRun?: string
  draft: string
  images: ImageAttachment[]
  error?: string
}
interface Pending {
  controller: AbortController
  payload: QueryRequest
  timer?: ReturnType<typeof setTimeout>
  buffer: string
  generation: number
  lastSeq: number
  cancelling: boolean
}
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
  const loadingSession = ref(false)
  const error = ref('')
  const theme = ref(storage.get('rag-theme') || 'light')
  const pending = new Map<string, Pending>() // non-serializable resources stay outside Pinia state
  let loadVersion = 0
  let sessionController: AbortController | undefined
  let initVersion = 0
  let sessionsVersion = 0
  watch(model, (value) => storage.set('rag-model', value))
  watch(thinking, (value) => storage.set('rag-thinking', value))
  const current = computed(() => conversations.value[currentId.value])
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
      const messages = detail.messages
      for (const run of detail.runs ?? []) {
        if (run.status === 'success' || messages.some((m) => m.run_id === run.id)) continue
        messages.push({
          id: `${run.id}-user`,
          role: 'user',
          content: run.query,
          timestamp: run.started_at,
          run_id: run.id,
          attachments: run.attachments,
        })
        messages.push({
          id: `${run.id}-assistant`,
          role: 'assistant',
          content: run.result?.answer || '',
          timestamp: run.started_at,
          run_id: run.id,
          status: run.status === 'running' ? 'error' : run.status,
          notice:
            run.error ||
            (run.status === 'running'
              ? '此运行未连接到当前页面，请等待原页面完成后刷新。'
              : '本轮已停止，以下内容是未完成草稿。'),
        })
      }
      messages.sort((a, b) => a.timestamp - b.timestamp)
      conversations.value[id] = {
        id,
        title: detail.session_title,
        messages,
        events: detail.trace,
        status: 'idle',
        draft: '',
        images: [],
      }
      const lastRun = detail.runs?.at(-1)
      if (lastRun && ['error', 'cancelled'].includes(lastRun.status)) {
        conversations.value[id]!.draft = lastRun.query
        conversations.value[id]!.images = lastRun.attachments ?? []
      }
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
      if (!status.model_profiles.some((p) => p.id === model.value))
        model.value = status.default_model_profile
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
  function flush(run: Pending, assistant: Message) {
    if (run.timer) clearTimeout(run.timer)
    run.timer = undefined
    if (run.buffer) {
      assistant.content += run.buffer
      run.buffer = ''
    }
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
      context: { thinking_mode: thinking.value },
    }
    const run: Pending = {
      controller: new AbortController(),
      payload,
      buffer: '',
      generation: 0,
      lastSeq: 0,
      cancelling: false,
    }
    pending.set(id, run)
    conversation.activeRun = id
    conversation.status = 'submitting'
    conversation.error = ''
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
    selectedRun.value = id
    if (!sessions.value.some((s) => s.session_id === conversation.id))
      sessions.value.unshift({
        session_id: conversation.id,
        session_title: conversation.title,
        preview: query,
        turn_count: 0,
        updated_at: timestamp,
      })
    const onEvent = (event: ExecutionEvent) => {
      if (event.run_id !== id || event.session_id !== conversation.id || event.seq <= run.lastSeq)
        return
      run.lastSeq = event.seq
      if (event.type !== 'delta')
        conversation.events.push(
          event.type === 'completed'
            ? {
                ...event,
                data: {
                  result: { ...event.data.result, execution_trace: undefined, messages: undefined },
                },
              }
            : event,
        )
      switch (event.type) {
        case 'answer_start':
          flush(run, assistant)
          assistant.content = ''
          run.generation = event.data.generation
          break
        case 'delta':
          if (event.data.generation !== run.generation) break
          conversation.status = 'streaming'
          assistant.status = 'streaming'
          run.buffer += event.data.text
          run.timer ??= setTimeout(() => flush(run, assistant), 60)
          break
        case 'transport':
          assistant.notice = event.data.message
          break
        case 'notice':
          assistant.notice = event.data.message
          break
        case 'completed':
          flush(run, assistant)
          assistant.content = event.data.result.answer
          assistant.result = event.data.result
          assistant.status = conversation.status = 'success'
          assistant.notice = event.data.result.model_error || ''
          conversation.title = event.data.result.session_title || conversation.title
          break
        case 'error':
          flush(run, assistant)
          assistant.status = conversation.status = 'error'
          assistant.notice = event.data.message
          break
        case 'cancelled':
          flush(run, assistant)
          assistant.status = conversation.status = 'cancelled'
          assistant.notice = event.data.message
          break
      }
    }
    try {
      const response = await api.stream(payload, run.controller.signal)
      await readEvents(response, onEvent, { run_id: id, session_id: conversation.id })
    } catch (e) {
      flush(run, assistant)
      if (!['success', 'cancelled', 'error'].includes(assistant.status ?? '')) {
        assistant.status = conversation.status = run.cancelling ? 'cancelled' : 'error'
        assistant.notice = run.cancelling ? '已停止接收。取消结果以服务端记录为准。' : messageOf(e)
      }
    } finally {
      flush(run, assistant)
      pending.delete(id)
      if (conversation.activeRun === id) conversation.activeRun = undefined
      if (assistant.status === 'error' || assistant.status === 'cancelled') {
        if (!conversation.draft) conversation.draft = query
        if (!conversation.images.length) conversation.images = payload.images
      }
      await refreshSessions().catch(() => {
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
      const conversation = conversations.value[run.payload.session_id]
      const assistant = conversation?.messages.find((m) => m.id === `${id}-assistant`)
      // Completion can win the race against cancellation; the committed server result wins.
      if (response.run?.status === 'success' && response.run.result && assistant && conversation) {
        run.buffer = ''
        assistant.content = response.run.result.answer
        assistant.result = response.run.result
        assistant.status = conversation.status = 'success'
        assistant.notice = '本轮已在取消前完成。'
      }
      if (pending.has(id)) run.controller.abort()
    } catch {
      if (current.value?.activeRun === id)
        current.value.error = '取消确认失败，已断开连接。服务端将在检测断开后停止，请刷新核对。'
      run.controller.abort()
    }
  }
  function dispose() {
    initVersion++
    sessionsVersion++
    loadVersion++
    sessionController?.abort()
    for (const [id, run] of pending) {
      void api.cancel(id).catch(() => undefined)
      run.controller.abort()
      if (run.timer) clearTimeout(run.timer)
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
