import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { readEvents } from '../../src/api/sse'
import { api, checked, ApiError, requestJson } from '../../src/api/client'
import { useWorkbench } from '../../src/stores/workbench'
import { useKnowledge } from '../../src/stores/knowledge'
import { knowledgeApi } from '../../src/api/knowledge'
import MarkdownContent from '../../src/components/MarkdownContent.vue'
import { ActiveRun } from '../../src/chat/activeRun'
import { createDraftStorage } from '../../src/chat/drafts'
import { exportConversation } from '../../src/chat/export'
import type { Conversation } from '../../src/types/chat'
import type { ExecutionEvent, SessionDetail, SystemStatus } from '../../src/types'

const event = (type: string, data: object, seq = 1, run = 'r', session = 's') => ({
  type,
  data,
  seq,
  run_id: run,
  session_id: session,
  timestamp: 1,
})
const frame = (e: object) => `event: progress\r\ndata: ${JSON.stringify(e)}\r\n\r\n`
function response(text: string, bytewise = false) {
  const bytes = new TextEncoder().encode(text)
  return new Response(
    new ReadableStream({
      start(c) {
        if (bytewise) for (const b of bytes) c.enqueue(Uint8Array.of(b))
        else c.enqueue(bytes)
        c.close()
      },
    }),
    { headers: { 'content-type': 'text/event-stream' } },
  )
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})
afterEach(() => vi.restoreAllMocks())

it('exports failed and successful rounds in conversation order without repeating questions', () => {
  let exported: Blob | undefined
  const create = vi.spyOn(URL, 'createObjectURL').mockImplementation(blob => {
    exported = blob as Blob
    return 'blob:export-fixture'
  })
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  exportConversation({
    session_id: 's', session_title: 'ordered', trace: [],
    messages: [
      { id: 'success-user', run_id: 'success', role: 'user', content: 'later question', timestamp: 2 },
      { id: 'success-assistant', run_id: 'success', role: 'assistant', content: 'final answer', timestamp: 2 },
    ],
    runs: [
      { id: 'cancelled', session_id: 's', status: 'cancelled', query: 'earlier question', started_at: 1, result: { answer: 'partial draft', sources: [], session_id: 's' } },
      { id: 'success', session_id: 's', status: 'success', query: 'later question', started_at: 2 },
    ],
  })
  expect(create).toHaveBeenCalledOnce()
  return new Promise<void>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const text = String(reader.result)
        expect(text.indexOf('earlier question')).toBeLessThan(text.indexOf('later question'))
        expect(text.indexOf('partial draft')).toBeLessThan(text.indexOf('final answer'))
        expect(text.match(/earlier question/g)).toHaveLength(1)
        expect(text).toContain('已取消')
        resolve()
      } catch (error) { reject(error) }
    }
    reader.onerror = reject
    reader.readAsText(exported!)
  })
})

it('stops reading immediately and keeps input locked until cancellation acknowledgement', async () => {
  const store = setupStore()
  let transport!: AbortSignal
  vi.spyOn(api, 'stream').mockImplementation(async (_, signal) => {
    transport = signal
    return new Response(new ReadableStream({ start(controller) {
      signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')))
    } }), { headers: { 'content-type': 'text/event-stream' } })
  })
  let acknowledge!: () => void
  vi.spyOn(api, 'cancel').mockImplementation(() => new Promise(resolve => { acknowledge = () => resolve({ cancelled: true }) }))
  store.current!.draft = 'cancel fixture'
  const sending = store.send()
  const stopping = store.cancel()
  expect(transport.aborted).toBe(true)
  expect(store.current!.cancelling).toBe(true)
  expect(store.busy).toBe(true)
  acknowledge()
  await stopping
  await sending
  expect(store.busy).toBe(false)
  expect(store.current!.draft).toBe('cancel fixture')
  expect(store.current!.cancelling).toBe(false)
  store.dispose()
})

it('persists bounded text drafts with selections and excludes attachments', () => {
  const store = setupStore()
  store.current!.draft = 'unsent question'
  store.current!.knowledgeBaseId = 'library-a'
  store.current!.images = [{ name: 'private-image', data_url: 'data:image/png;base64,fixture' }]
  const storage = createDraftStorage()
  storage.save(store.current!)
  storage.flush()
  expect(localStorage.getItem('rag-text-drafts-v1')).not.toContain('private-image')
  expect(createDraftStorage().get(store.currentId)).toMatchObject({ draft: 'unsent question', knowledgeBaseId: 'library-a' })
  storage.remove(store.currentId)
  expect(createDraftStorage().get(store.currentId)).toBeUndefined()
  store.current!.draft = ''
  store.dispose()
})

it('parses Chinese UTF-8 byte boundaries, CRLF, heartbeats and multiple frames', async () => {
  const events: ExecutionEvent[] = []
  await readEvents(
    response(
      ': heartbeat\r\n\r\n' +
        frame(event('delta', { text: '你好', generation: 1 })) +
        frame(event('completed', { result: { answer: '最终回答' } }, 2)),
      true,
    ),
    (e) => events.push(e),
  )
  expect(events.map((e) => e.type)).toEqual(['delta', 'completed'])
  expect(events[0]?.data).toMatchObject({ text: '你好' })
})

it('rejects unexpected EOF and mismatched terminal identity', async () => {
  await expect(
    readEvents(response(frame(event('delta', { text: '草稿', generation: 1 }))), () => {}),
  ).rejects.toThrow('连接中断')
  await expect(
    readEvents(response(frame(event('completed', { result: { answer: 'x' } }))), () => {}, {
      run_id: 'other',
      session_id: 's',
    }),
  ).rejects.toThrow('不匹配')
})

it('renders code and removes executable HTML and unsafe links', () => {
  const wrapper = mount(MarkdownContent, {
    props: {
      content:
        '<img src=x onerror=alert(1)>\n<script>alert(1)</script>\n[x](javascript:alert(1))\n```js\nconst n = 1\n```',
    },
  })
  expect(wrapper.find('script').exists()).toBe(false)
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false)
  expect(wrapper.find('code').text()).toContain('const n = 1')
  wrapper.unmount()
})

function setupStore() {
  const store = useWorkbench()
  store.system = {
    default_model_profile: 'fixture',
    model_profiles: [{ id: 'fixture', supports_vision: true, configured: true }],
  } as SystemStatus
  store.model = 'fixture'
  store.newChat()
  vi.spyOn(api, 'sessions').mockResolvedValue({ items: [] })
  return store
}

it('links only backend citations outside code and existing links', async () => {
  const wrapper = mount(MarkdownContent, { props: { content: '证据 [S1]，未知 [S9]。`[S1]`\n\n[链接 [S1]](https://example.com)\n\n```text\n[S1]\n```', sources: [{ citation_id: 'S1', source: 'doc' }] } })
  expect(wrapper.findAll('.citation-link')).toHaveLength(1)
  await wrapper.get('.citation-link').trigger('click')
  expect(wrapper.emitted('citation')).toEqual([['S1']])
  expect(wrapper.find('code').text()).toContain('[S1]')
  wrapper.unmount()
})

it('preserves field paths without echoing validation input or sensitive messages', async () => {
  const response = new Response(JSON.stringify({ detail: [{ loc: ['body', 'models', 0, 'model_name'], type: 'string_pattern_mismatch', msg: 'secret-fixture', input: 'secret-fixture' }, { loc: ['body', 'api_key'], type: 'value_error', msg: 'secret-fixture' }] }), { status: 422 })
  const error = await checked(response).catch((cause: unknown) => cause)
  expect(error).toBeInstanceOf(ApiError)
  expect(error).toMatchObject({ issues: [{ field: 'models.0.model_name', message: '格式不正确，请勿包含空格' }, { field: 'api_key', message: '凭据格式或长度不符合要求' }] })
  expect(JSON.stringify(error)).not.toContain('secret-fixture')
})

it('isolates a running conversation and replaces revision drafts with one final answer', async () => {
  const store = setupStore()
  const firstId = store.currentId
  let push!: ReadableStreamDefaultController<Uint8Array>
  const stream = vi.spyOn(api, 'stream').mockImplementation(
    async () =>
      new Response(
        new ReadableStream({
          start(c) {
            push = c
          },
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      ),
  )
  store.current!.draft = 'first'
  const running = store.send()
  await store.send('duplicate')
  expect(stream).toHaveBeenCalledTimes(1)
  const runId = store.current!.activeRun!
  store.newChat()
  const send = (type: string, data: object, seq: number) =>
    push.enqueue(new TextEncoder().encode(frame(event(type, data, seq, runId, firstId))))
  send('answer_start', { generation: 1 }, 1)
  send('delta', { text: 'old draft', generation: 1 }, 2)
  send('answer_start', { generation: 2 }, 3)
  send('delta', { text: 'new draft', generation: 2 }, 4)
  send('completed', { result: { answer: 'final', sources: [] } }, 5)
  await running
  expect(store.current!.messages).toHaveLength(0)
  expect(store.conversations[firstId]!.messages.at(-1)?.content).toBe('final')
  expect(store.conversations[firstId]!.activeRun).toBeUndefined()
})

it('restores input on disconnect and allows a manual retry', async () => {
  const store = setupStore()
  vi.spyOn(api, 'stream').mockResolvedValue(response(''))
  store.current!.draft = 'retry question'
  await store.send()
  expect(store.current!.status).toBe('error')
  expect(store.current!.draft).toBe('retry question')
  expect(store.busy).toBe(false)
  await store.send()
  expect(api.stream).toHaveBeenCalledTimes(2)
  expect(store.current!.messages).toHaveLength(4)
})

it('keeps the saved session when initialization is interrupted', async () => {
  localStorage.setItem('rag-session-live', 'saved-session')
  localStorage.setItem('rag-session-demo', 'retired-session')
  localStorage.setItem('rag-mode', 'demo')
  const store = useWorkbench()
  vi.spyOn(api, 'status').mockRejectedValue(new Error('network interruption'))
  await store.initialize()
  expect(store.current).toBeDefined()
  expect(localStorage.getItem('rag-session')).toBe('saved-session')
  expect(localStorage.getItem('rag-session-demo')).toBeNull()
  expect(localStorage.getItem('rag-mode')).toBeNull()
})

it('uses the committed answer when completion wins the cancel race', async () => {
  const store = setupStore()
  vi.spyOn(api, 'stream').mockImplementation(
    async (_, signal) =>
      new Response(
        new ReadableStream({
          start(c) {
            signal.addEventListener('abort', () =>
              c.error(new DOMException('aborted', 'AbortError')),
            )
          },
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      ),
  )
  store.current!.draft = 'question'
  const running = store.send()
  vi.spyOn(api, 'cancel').mockResolvedValue({
    cancelled: false,
    run: {
      status: 'success',
      result: { answer: 'committed', session_id: store.currentId, sources: [] },
    },
  })
  await store.cancel()
  await running
  expect(store.current!.status).toBe('success')
  expect(store.current!.messages.at(-1)?.content).toBe('committed')
  expect(store.current!.draft).toBe('')
})


it('restores library scope per conversation and never falls back when a library disappears', async () => {
  const store = setupStore()
  const knowledge = useKnowledge()
  const first = store.currentId
  knowledge.selectedId = 'library-a'
  store.searchScope = 'all'
  store.newChat()
  knowledge.selectedId = 'library-b'
  await store.loadSession(first)
  expect(knowledge.selectedId).toBe('library-a')
  expect(store.searchScope).toBe('all')
  vi.spyOn(knowledgeApi, 'list').mockResolvedValue({ items: [], limits: knowledge.limits })
  await knowledge.refresh()
  expect(knowledge.selectedId).toBe('library-a')
  store.dispose()
})

it('reports an HTML proxy response without parsing or displaying the page body', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('<html>private page</html>', {
    headers: { 'content-type': 'text/html; charset=utf-8' },
  }))
  await expect(requestJson('/knowledge')).rejects.toThrow('接口未返回 JSON')
})

it('prepends history without overwriting live state and ignores an aborted older page', async () => {
  const store = setupStore()
  const page = (id: string): SessionDetail => ({
    session_id: 'saved', session_title: 'saved', trace: [], runs: [],
    messages: [{ id, role: 'user', content: id, timestamp: id === 'latest' ? 2 : 1 }],
    history_page: { next_cursor: id === 'latest' ? 'cursor' : null },
  })
  const read = vi.spyOn(api, 'session').mockResolvedValue(page('latest'))
  await store.loadSession('saved')
  expect(read.mock.calls[0]?.[2]).toEqual({ limit: 20 })
  const conversation = store.current!
  conversation.draft = 'keep editing'
  conversation.knowledgeBaseId = 'selected-kb'
  conversation.activeRun = 'live'
  conversation.status = 'streaming'
  read.mockRejectedValueOnce(new Error('temporary failure'))
  expect(await store.loadEarlier()).toBe(false)
  expect(conversation.historyError).toBe('temporary failure')
  expect(conversation.historyCursor).toBe('cursor')
  let resolve!: (value: SessionDetail) => void
  read.mockImplementationOnce(() => new Promise(r => { resolve = r }))
  const pending = store.loadEarlier()
  expect(await store.loadEarlier()).toBe(false)
  store.newChat()
  resolve(page('stale'))
  expect(await pending).toBe(false)
  expect(conversation.messages.map(m => m.id)).toEqual(['latest'])
  await store.loadSession('saved')
  read.mockResolvedValue({ ...page('older'), messages: [...page('older').messages, ...page('latest').messages],
    trace: [event('started', { mode: 'live' }, 1, 'live', 'saved') as ExecutionEvent] })
  expect(await store.loadEarlier()).toBe(true)
  expect(conversation.messages.map(m => m.id)).toEqual(['older', 'latest'])
  expect(conversation.events).toEqual([]) // The active stream owns its event sequence.
  expect(conversation).toMatchObject({ draft: 'keep editing', knowledgeBaseId: 'selected-kb', activeRun: 'live', status: 'streaming', historyCursor: null, loadingHistory: false })
  store.dispose()
})

it.each(['cancelled', 'error'] as const)('restores a first %s run snapshot and retries the selected conversation only', async (status) => {
  const store = setupStore()
  const knowledge = useKnowledge()
  vi.spyOn(api, 'session').mockResolvedValue({
    session_id: 'saved', session_title: 'saved question', messages: [], trace: [], runs: [{
      id: 'old-run', session_id: 'saved', status, started_at: 1, query: 'retry question',
      request: { knowledge_base_id: 'library-a', search_scope: 'all', thinking_mode: 'deep', model_profile: 'fixture' },
    }],
  })
  await store.loadSession('saved')
  expect(knowledge.selectedId).toBe('library-a')
  expect(store.searchScope).toBe('all')
  expect(store.thinking).toBe('deep')
  expect(store.current?.status).toBe(status)
  expect(store.current?.draft).toBe('retry question')
  store.newChat()
  knowledge.selectedId = 'library-b'
  store.thinking = 'retrieval'
  await store.loadSession('saved')
  vi.spyOn(api, 'stream').mockResolvedValue(response(''))
  await store.send()
  expect(api.stream).toHaveBeenCalledWith(expect.objectContaining({ model_profile: 'fixture',
    context: { knowledge_base_id: 'library-a', search_scope: 'all', thinking_mode: 'deep' },
  }), expect.any(AbortSignal))
  expect(store.busy).toBe(false)
  store.dispose()
})

it('checks distinct deletion and document response contracts', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify({ status: 'deleting' }), {
    headers: { 'content-type': 'application/json' },
  }))
  await expect(knowledgeApi.deleteDocument('kb', 'doc')).resolves.toEqual({ status: 'deleting' })
  await expect(knowledgeApi.retryDocument('kb', 'doc')).rejects.toThrow('响应格式')
})

it('a late cancellation confirmation may fix the old answer but cannot release or finish a newer run', () => {
  const assistant: Conversation['messages'][number] = { id: 'old-assistant', role: 'assistant', content: '', timestamp: 1 }
  const conversation: Conversation = { id: 's', title: 'old', messages: [assistant], events: [], status: 'submitting', activeRun: 'old', draft: '', images: [] }
  const run = new ActiveRun({ query: 'old', session_id: 's', run_id: 'old', model_profile: 'fixture', images: [], context: { thinking_mode: '' } }, conversation, assistant)
  run.fail(new Error('disconnected'))
  run.release()
  conversation.activeRun = 'new'
  conversation.status = 'streaming'
  conversation.title = 'new'
  conversation.messages.push({ id: 'new-assistant', role: 'assistant', content: '', timestamp: 2 })
  run.complete({ answer: 'committed old answer', sources: [], session_id: 's', session_title: 'old' })
  run.release()
  expect(assistant.status).toBe('success')
  expect(conversation).toMatchObject({ activeRun: 'new', status: 'streaming', title: 'new' })
})
