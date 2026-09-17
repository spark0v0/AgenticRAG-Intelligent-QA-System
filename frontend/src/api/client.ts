import type { QueryRequest, RunRecord, SessionDetail, SessionSummary, SystemStatus } from '../types'

export async function checked(response: Response): Promise<Response> {
  if (response.ok) return response
  let message = `请求失败（HTTP ${response.status}）`
  try {
    const payload = (await response.json()) as { detail?: unknown }
    if (typeof payload.detail === 'string') message = payload.detail
    else if (Array.isArray(payload.detail))
      message = '输入参数不符合要求，请检查文字长度、图片类型和大小。'
  } catch {
    /* Preserve the gateway status when no JSON body is available. */
  }
  throw new Error(message)
}

export async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await checked(
    await fetch(`/api${path}`, {
      ...init,
      signal: init.signal ?? AbortSignal.timeout(30000),
    }),
  )
  return response.json() as Promise<T>
}

export const api = {
  status: () => requestJson<SystemStatus>('/status'),
  sessions: () => requestJson<{ items: SessionSummary[] }>('/sessions'),
  session: (id: string, signal?: AbortSignal) =>
    requestJson<SessionDetail>(`/sessions/${encodeURIComponent(id)}`, { signal }),
  cancel: (id: string) =>
    requestJson<{ cancelled: boolean; run?: Pick<RunRecord, 'status' | 'result' | 'error'> }>(
      `/runs/${encodeURIComponent(id)}/cancel`,
      { method: 'POST' },
    ),
  stream: (payload: QueryRequest, signal: AbortSignal) =>
    fetch('/api/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(payload),
      signal,
    }).then(checked),
}
