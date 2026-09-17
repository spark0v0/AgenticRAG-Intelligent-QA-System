import type { QueryRequest, RunRecord, SessionDetail, SessionSummary, SystemStatus } from '../types'

export interface FieldIssue {
  field: string
  message: string
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public issues: FieldIssue[] = [],
  ) {
    super(message)
    this.name = 'ApiError'
  }
}
const validationMessages: Record<string, string> = {
  string_too_short: '请填写此字段',
  string_too_long: '内容超过长度限制',
  string_pattern_mismatch: '格式不正确，请勿包含空格',
  greater_than_equal: '数值低于允许范围',
  less_than_equal: '数值超过允许范围',
  int_parsing: '请输入整数',
  int_from_float: '请输入整数',
  literal_error: '请选择有效选项',
  too_long: '项目数量超过限制',
  missing: '请填写此字段',
}
const safeValidationMessages = new Set([
  '地址必须是无凭据、查询参数的 HTTP(S) 服务地址',
  '远程供应商必须使用 HTTPS，本机服务可使用 HTTP',
  '同一供应商中模型 ID 不可重复',
])
export async function checked(response: Response): Promise<Response> {
  if (response.ok) return response
  let message = `请求失败（HTTP ${response.status}）`
  const issues: FieldIssue[] = []
  try {
    const payload = (await response.json()) as { detail?: unknown }
    if (typeof payload.detail === 'string') message = payload.detail
    else if (Array.isArray(payload.detail)) {
      for (const item of payload.detail) {
        if (!item || typeof item !== 'object' || !Array.isArray(item.loc)) continue
        const field = item.loc
          .filter((part: unknown) => typeof part === 'string' || typeof part === 'number')
          .filter((part: unknown) => part !== 'body')
          .join('.')
        const detail = typeof item.msg === 'string' ? item.msg.replace(/^Value error, /, '') : ''
        // Never render validation input/ctx or arbitrary messages that might contain credentials.
        const label = safeValidationMessages.has(detail)
          ? detail
          : validationMessages[String(item.type)] || '内容不符合接口要求'
        issues.push({ field, message: field === 'api_key' ? '凭据格式或长度不符合要求' : label })
      }
      message = issues.find((issue) => !issue.field)?.message || '提交内容有误，请检查标记的字段。'
    }
  } catch {
    /* Preserve the gateway status when no JSON body is available. */
  }
  throw new ApiError(message, response.status, issues)
}

export async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await checked(
    await fetch(`/api${path}`, {
      ...init,
      signal: init.signal
        ? AbortSignal.any([init.signal, AbortSignal.timeout(30000)])
        : AbortSignal.timeout(30000),
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
