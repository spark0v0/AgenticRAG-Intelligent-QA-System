import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { readEvents } from '../../src/api/sse'
import { api, checked, ApiError } from '../../src/api/client'
import { useWorkbench } from '../../src/stores/workbench'
import MarkdownContent from '../../src/components/MarkdownContent.vue'
import type { ExecutionEvent, SystemStatus } from '../../src/types'

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
