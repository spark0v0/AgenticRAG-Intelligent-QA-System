import type { SessionDetail } from '../types'
import { restoreConversation } from './history'

export function exportConversation(detail: SessionDetail) {
  const lines = [`# ${detail.session_title}`, '']
  const runStatuses = new Map(detail.runs.map((run) => [run.id, run.status]))
  const unfinished: Record<string, string> = {
    running: '生成中，内容尚未完成',
    error: '失败',
    cancelled: '已取消',
  }
  // Reuse the same merge/order rules as history restoration, including unfinished rounds.
  for (const message of restoreConversation(detail).messages) {
    const status = (message.run_id && runStatuses.get(message.run_id)) || message.status
    const label = message.role === 'assistant' && status ? unfinished[status] : undefined
    lines.push(`## ${message.role === 'user' ? '提问' : '回答'}`, '', message.content, '')
    if (label) lines.push(`状态：${label}`, message.notice || '', '')
    for (const source of message.result?.source_map ?? [])
      lines.push(
        `- [${source.citation_id}] ${source.document_name || source.source}${source.page ? ` · 第 ${source.page} 页` : ''}`,
        source.excerpt || '',
        '',
      )
  }
  const url = URL.createObjectURL(
    new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `${detail.session_title.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').slice(0, 60) || '会话'}.md`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
