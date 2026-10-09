import type { ExecutionEvent, Message, QueryRequest, QueryResult, RunStatus } from '../types'
import type { Conversation } from '../types/chat'

const phases: Record<string, string> = {
  router: '正在识别请求…',
  planner: '正在规划检索子问题…',
  retriever: '正在检索证据…',
  generator: '正在等待模型回答…',
  critic: '正在检查证据引用…',
}
const terminal = (status?: RunStatus) =>
  status === 'success' || status === 'error' || status === 'cancelled'

// One instance owns one transport, buffer and timer, independent of the selected conversation.
export class ActiveRun {
  readonly controller = new AbortController()
  cancelling = false
  private timer?: ReturnType<typeof setTimeout>
  private buffer = ''
  private generation = 0
  private lastSeq = 0

  constructor(
    readonly payload: QueryRequest,
    private conversation: Conversation,
    private assistant: Message,
  ) {
    this.setStatus('submitting')
  }
  private setStatus(status: RunStatus) {
    this.assistant.status = status
    if (
      this.conversation.activeRun === this.payload.run_id ||
      (!this.conversation.activeRun && this.conversation.messages.at(-1) === this.assistant)
    )
      this.conversation.status = status
    if (terminal(status)) this.assistant.phase = undefined
  }
  flush() {
    clearTimeout(this.timer)
    this.timer = undefined
    this.assistant.content += this.buffer
    this.buffer = ''
  }
  complete(result: QueryResult, notice = result.model_error || '') {
    // The committed server result wins even when the cancel response arrives after disconnect.
    this.flush()
    this.assistant.content = result.answer
    this.assistant.result = result
    this.assistant.notice = notice
    if (this.conversation.messages.at(-1) === this.assistant)
      this.conversation.title = result.session_title || this.conversation.title
    this.setStatus('success')
  }
  receive = (event: ExecutionEvent) => {
    if (
      event.run_id !== this.payload.run_id ||
      event.session_id !== this.payload.session_id ||
      event.seq <= this.lastSeq ||
      terminal(this.assistant.status)
    )
      return
    this.lastSeq = event.seq
    if (event.type !== 'delta')
      this.conversation.events.push(
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
      case 'stage':
        if (event.data.status === 'running')
          this.assistant.phase = phases[event.data.node] || '正在执行…'
        break
      case 'answer_start':
        this.flush()
        this.assistant.content = ''
        this.generation = event.data.generation
        break
      case 'delta':
        if (event.data.generation !== this.generation) break
        this.setStatus('streaming')
        this.buffer += event.data.text
        this.timer ??= setTimeout(() => this.flush(), 60)
        break
      case 'transport':
      case 'notice':
        this.assistant.notice = event.data.message
        break
      case 'completed':
        this.complete(event.data.result)
        break
      case 'error':
      case 'cancelled':
        this.flush()
        this.setStatus(event.type)
        this.assistant.notice = event.data.message
        break
    }
  }
  fail(cause: unknown) {
    this.flush()
    if (terminal(this.assistant.status)) return
    this.setStatus(this.cancelling ? 'cancelled' : 'error')
    this.assistant.notice = this.cancelling
      ? '已停止接收。取消结果以服务端记录为准。'
      : cause instanceof Error
        ? cause.message
        : '请求失败，请稍后重试。'
  }
  release() {
    this.flush()
    if (this.conversation.activeRun !== this.payload.run_id) return
    this.conversation.activeRun = undefined
    if (this.assistant.status === 'error' || this.assistant.status === 'cancelled') {
      if (!this.conversation.draft) this.conversation.draft = this.payload.query
      if (!this.conversation.images.length) this.conversation.images = this.payload.images
    }
  }
  abort() {
    this.controller.abort()
    this.flush()
  }
}
