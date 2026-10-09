import { requestJson } from './client'
import { documentResponse, deletionResponse } from './knowledgeContract'
import type {
  Evidence,
  KnowledgeDocument,
  KnowledgeLibrary,
  KnowledgeMode,
  UploadLimits,
} from '../types/knowledge'
import type { Source } from '../types'

const headers = { 'Content-Type': 'application/json', 'X-Workbench-Request': '1' }
const base = (id: string) => `/knowledge/${encodeURIComponent(id)}`
export const knowledgeApi = {
  list: (signal?: AbortSignal) =>
    requestJson<{ items: KnowledgeLibrary[]; limits: UploadLimits }>('/knowledge', { signal }),
  create: (name: string, mode: KnowledgeMode, signal?: AbortSignal) =>
    requestJson<KnowledgeLibrary>('/knowledge', {
      method: 'POST',
      headers,
      body: JSON.stringify({ name, mode }),
      signal,
    }),
  rename: (id: string, name: string, signal?: AbortSignal) =>
    requestJson<KnowledgeLibrary>(base(id), {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ name }),
      signal,
    }),
  remove: (id: string, signal?: AbortSignal) =>
    requestJson<{ status: string; message?: string }>(base(id), {
      method: 'DELETE',
      headers,
      signal,
    }),
  documents: (id: string, signal?: AbortSignal) =>
    requestJson<{ items: KnowledgeDocument[] }>(`${base(id)}/documents`, { signal }),
  upload: (id: string, files: File[], signal?: AbortSignal) => {
    const body = new FormData()
    files.forEach((file) => body.append('files', file))
    return requestJson<{ items: { document: KnowledgeDocument; duplicate: boolean }[] }>(
      `${base(id)}/documents`,
      { method: 'POST', headers: { 'X-Workbench-Request': '1' }, body, signal },
    )
  },
  retryDocument: async (id: string, doc: string, signal?: AbortSignal) =>
    documentResponse(
      await requestJson<unknown>(`${base(id)}/documents/${encodeURIComponent(doc)}/retry`, {
        method: 'POST',
        headers,
        signal,
      }),
      id,
      doc,
    ),
  cancelDocument: async (id: string, doc: string, signal?: AbortSignal) =>
    documentResponse(
      await requestJson<unknown>(`${base(id)}/documents/${encodeURIComponent(doc)}/cancel`, {
        method: 'POST',
        headers,
        signal,
      }),
      id,
      doc,
    ),
  deleteDocument: async (id: string, doc: string, signal?: AbortSignal) =>
    deletionResponse(
      await requestJson<unknown>(`${base(id)}/documents/${encodeURIComponent(doc)}`, {
        method: 'DELETE',
        headers,
        signal,
      }),
    ),
  evidence: (source: Source, signal?: AbortSignal) =>
    requestJson<Evidence>(
      `${base(source.knowledge_base_id!)}/documents/${encodeURIComponent(source.document_id!)}/evidence/${encodeURIComponent(source.chunk_id!)}`,
      { signal },
    ),
  original: (source: Source) =>
    `/api${base(source.knowledge_base_id!)}/documents/${encodeURIComponent(source.document_id!)}/original`,
  search: (
    id: string,
    query: string,
    mode: 'keyword' | 'semantic' | 'hybrid',
    signal?: AbortSignal,
  ) =>
    requestJson<{
      documents: {
        content: string
        source: string
        metadata: Omit<Source, 'citation_id' | 'source'>
      }[]
      metadata: { state: string; mode: string }
    }>(`${base(id)}/search`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query, mode }),
      signal,
    }),
}
