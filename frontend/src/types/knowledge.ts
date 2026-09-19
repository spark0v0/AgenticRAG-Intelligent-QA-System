export type KnowledgeMode = 'keyword' | 'hybrid'
export type IndexStatus =
  | 'queued'
  | 'parsing'
  | 'splitting'
  | 'indexing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'deleting'
  | 'delete_failed'
  | 'deleted'
export interface KnowledgeLibrary {
  id: string
  name: string
  mode: KnowledgeMode
  created: number
  document_count: number
  ready_count: number
  deleting: number
}
export interface IndexJob {
  id: string
  action: 'index' | 'delete'
  status: IndexStatus
  processed: number
  total: number | null
  error: string | null
}
export interface KnowledgeDocument {
  id: string
  kb_id: string
  name: string
  ext: string
  size: number
  version: string
  status: IndexStatus
  chunk_count: number
  error: string | null
  created: number
  original_available: boolean
  needs_rebuild: boolean
  job: IndexJob | null
}
export interface UploadLimits {
  files: number
  file_bytes: number
  request_bytes: number
  extensions: string[]
}
export interface Evidence {
  original_available: boolean
  document_name: string
  version: string
  content: string | null
  position: { page: number | null; heading: string; start: number; end: number } | null
}
export const indexLabels: Record<IndexStatus, string> = {
  queued: '等待索引',
  parsing: '提取文字',
  splitting: '切分片段',
  indexing: '写入索引',
  completed: '可检索',
  failed: '索引失败',
  cancelled: '已取消',
  deleting: '正在清理',
  delete_failed: '清理失败',
  deleted: '已删除',
}
export const activeIndex = (status?: IndexStatus) =>
  !!status && ['queued', 'parsing', 'splitting', 'indexing', 'deleting'].includes(status)
