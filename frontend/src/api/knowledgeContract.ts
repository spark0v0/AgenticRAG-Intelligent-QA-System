import type { IndexStatus, KnowledgeDocument } from '../types/knowledge'
import { indexLabels } from '../types/knowledge'

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
const status = (value: unknown): value is IndexStatus =>
  typeof value === 'string' && Object.hasOwn(indexLabels, value)
const number = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)
const nullableText = (value: unknown) => value === null || typeof value === 'string'

export function isDocument(value: unknown): value is KnowledgeDocument {
  if (
    !record(value) ||
    typeof value.id !== 'string' ||
    typeof value.kb_id !== 'string' ||
    typeof value.name !== 'string' ||
    typeof value.ext !== 'string' ||
    typeof value.version !== 'string' ||
    !number(value.size) ||
    !number(value.chunk_count) ||
    !number(value.created) ||
    !status(value.status) ||
    !nullableText(value.error) ||
    typeof value.original_available !== 'boolean' ||
    typeof value.needs_rebuild !== 'boolean'
  )
    return false
  const job = value.job
  return (
    job === null ||
    (record(job) &&
      typeof job.id === 'string' &&
      (job.action === 'index' || job.action === 'delete') &&
      status(job.status) &&
      number(job.processed) &&
      (job.total === null || number(job.total)) &&
      nullableText(job.error))
  )
}

export function documentResponse(value: unknown, library: string, id: string): KnowledgeDocument {
  if (!isDocument(value) || value.kb_id !== library || value.id !== id)
    throw new Error('文档接口响应格式或所属知识库不符，请刷新核对。')
  return value
}

export function deletionResponse(value: unknown): { status: 'deleting' | 'deleted' } {
  if (!record(value) || (value.status !== 'deleting' && value.status !== 'deleted'))
    throw new Error('删除接口未返回有效状态，请刷新核对清理结果。')
  return { status: value.status }
}
