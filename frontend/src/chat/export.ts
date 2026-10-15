import type { SessionDetail } from '../types'

export function exportConversation(detail: SessionDetail) {
  const lines = [`# ${detail.session_title}`, '']
  for (const message of detail.messages) {
    lines.push(`## ${message.role === 'user' ? '提问' : '回答'}`, '', message.content, '')
    for (const source of message.result?.source_map ?? [])
      lines.push(
        `- [${source.citation_id}] ${source.document_name || source.source}${source.page ? ` · 第 ${source.page} 页` : ''}`,
        source.excerpt || '',
        '',
      )
  }
  for (const run of detail.runs.filter((item) => item.status !== 'success'))
    lines.push(
      '## 未完成的问答',
      '',
      run.query,
      '',
      run.result?.answer || '',
      `状态：${run.status}`,
      '',
    )
  const url = URL.createObjectURL(
    new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `${detail.session_title.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').slice(0, 60) || '会话'}.md`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
