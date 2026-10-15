import type { Source } from './index'

export type KnowledgeMode = 'keyword' | 'hybrid'
export type RetrievalMode = 'keyword' | 'semantic' | 'hybrid'
export type RetrievalState =
  'ready' | 'empty' | 'indexing' | 'not_ready' | 'no_match' | 'unavailable' | 'error'
export interface RetrievalDocument {
  content: string
  source: string
  score: number
  metadata: Omit<Source, 'citation_id' | 'source'>
  ranking?: {
    keyword_rank: number | null
    semantic_rank: number | null
    bm25_score: number | null
    cosine_similarity: number | null
    rrf_score: number
  }
}
export interface RetrievalResult {
  documents: RetrievalDocument[]
  metadata: {
    state: RetrievalState
    mode: RetrievalMode
    knowledge_base_id: string
    candidate_count: number
    reason?: string
  }
}
export interface RetrievalComparison {
  knowledge_base_id: string
  query: string
  candidate_count: number
  limit: number
  timings: {
    snapshot_ms: number
    keyword_ms: number | null
    semantic_ms: number | null
    fusion_ms: number | null
    total_ms: number
  }
  results: RetrievalResult[]
}
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
export const isSearchable = (doc: KnowledgeDocument) =>
  doc.status === 'completed' && !doc.needs_rebuild && doc.chunk_count > 0
