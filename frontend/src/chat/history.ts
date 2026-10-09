import type { RequestSnapshot, SearchScope, SessionDetail } from '../types'
import type { Conversation } from '../types/chat'

function isScope(value: unknown): value is SearchScope {
  return value === 'auto' || value === 'local' || value === 'web' || value === 'all'
}
function validSnapshot(value: unknown): value is RequestSnapshot {
  return (
    !!value &&
    typeof value === 'object' &&
    'knowledge_base_id' in value &&
    typeof value.knowledge_base_id === 'string' &&
    'search_scope' in value &&
    isScope(value.search_scope) &&
    'thinking_mode' in value &&
    typeof value.thinking_mode === 'string' &&
    ['', 'quick', 'retrieval', 'deep'].includes(value.thinking_mode) &&
    'model_profile' in value &&
    typeof value.model_profile === 'string'
  )
}

export function restoreConversation(detail: SessionDetail): Conversation {
  const messages = [...detail.messages]
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
  const lastRun = detail.runs?.at(-1)
  // Never recover an older run's snapshot over a newer run. Old records fall back explicitly.
  const request = validSnapshot(lastRun?.request) ? lastRun.request : undefined
  const legacy = messages.findLast((m) => m.result?.retrieval_plan)?.result?.retrieval_plan
  const retryable = lastRun?.status === 'error' || lastRun?.status === 'cancelled'
  return {
    id: detail.session_id,
    title: detail.session_title,
    messages,
    events: detail.trace,
    knowledgeBaseId: request?.knowledge_base_id ?? legacy?.knowledge_base_id,
    searchScope:
      request?.search_scope ?? (isScope(legacy?.search_scope) ? legacy.search_scope : 'auto'),
    modelProfile: request?.model_profile,
    thinkingMode: request?.thinking_mode,
    status:
      lastRun?.status === 'error'
        ? 'error'
        : lastRun?.status === 'cancelled'
          ? 'cancelled'
          : 'idle',
    draft: retryable ? lastRun.query : '',
    images: retryable ? (lastRun.attachments ?? []) : [],
    restoreNotice: request
      ? retryable
        ? '已恢复本轮问题、附件和请求选项；再次发送使用输入区当前选项。'
        : undefined
      : '旧会话未记录完整请求选项，已参考历史回答恢复检索范围；发送前请确认知识库、模式与模型。',
  }
}
