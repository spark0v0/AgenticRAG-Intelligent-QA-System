import type { ExecutionEvent } from '../types'

/** Incremental SSE framing. TextDecoder preserves UTF-8 across byte boundaries. */
export async function readEvents(
  response: Response,
  consume: (event: ExecutionEvent) => void,
  identity?: { run_id: string; session_id: string },
): Promise<void> {
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
    throw new Error('服务未返回事件流，请检查接口或代理配置。')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let buffer = ''
  let terminal = false
  const dispatch = (frame: string) => {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''))
      .join('\n')
    if (!data) return // comments/heartbeats
    const event: unknown = JSON.parse(data)
    if (!isEnvelope(event)) throw new Error('收到无效的执行事件。')
    if (identity && (event.run_id !== identity.run_id || event.session_id !== identity.session_id))
      throw new Error('流事件与本轮运行不匹配。')
    if (terminal) return
    consume(event)
    terminal = ['completed', 'error', 'cancelled'].includes(event.type)
  }
  try {
    while (!terminal) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      if (buffer.length > 16 * 1024 * 1024) throw new Error('单条流事件过大。')
      let separator: RegExpExecArray | null
      while ((separator = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, separator.index)
        buffer = buffer.slice(separator.index + separator[0].length)
        dispatch(frame)
      }
      if (done) break
    }
    if (!terminal) throw new Error('连接中断，未收到完成标记。草稿已保留，请手动重试。')
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}

function isEnvelope(value: unknown): value is ExecutionEvent {
  if (!value || typeof value !== 'object') return false
  const e = value as Record<string, unknown>
  if (
    typeof e.type !== 'string' ||
    typeof e.run_id !== 'string' ||
    typeof e.session_id !== 'string' ||
    typeof e.seq !== 'number' ||
    typeof e.timestamp !== 'number' ||
    !e.data ||
    typeof e.data !== 'object'
  )
    return false
  const data = e.data as Record<string, unknown>
  if (e.type === 'delta')
    return typeof data.text === 'string' && typeof data.generation === 'number'
  if (e.type === 'completed')
    return (
      !!data.result &&
      typeof data.result === 'object' &&
      typeof (data.result as Record<string, unknown>).answer === 'string'
    )
  if (e.type === 'answer_start') return typeof data.generation === 'number'
  if (e.type === 'error' || e.type === 'cancelled' || e.type === 'notice')
    return typeof data.message === 'string'
  if (e.type === 'sources') return Array.isArray(data.items)
  return ['started', 'stage', 'tool', 'transport', 'info', 'retrieval_round'].includes(e.type)
}
