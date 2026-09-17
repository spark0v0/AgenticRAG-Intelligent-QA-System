import { requestJson } from './client'
import type { ProviderList, ProviderSettings } from '../types'

function mutation(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Workbench-Request': '1' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}
export const settingsApi = {
  list: (signal?: AbortSignal) => requestJson<ProviderList>('/settings/providers', { signal }),
  save: (
    body: ProviderSettings & { api_key: string; clear_key: boolean },
    id?: string,
    signal?: AbortSignal,
  ) =>
    requestJson<{ id: string }>(`/settings/providers${id ? `/${encodeURIComponent(id)}` : ''}`, {
      ...mutation(id ? 'PUT' : 'POST', body),
      signal,
    }),
  remove: (id: string, signal?: AbortSignal) =>
    requestJson(`/settings/providers/${encodeURIComponent(id)}`, { ...mutation('DELETE'), signal }),
  check: (id: string, signal?: AbortSignal) =>
    requestJson<{ ok: boolean; message: string; models: string[] }>(
      `/settings/providers/${encodeURIComponent(id)}/check`,
      { ...mutation('POST'), signal },
    ),
  setDefault: (profile_id: string, signal?: AbortSignal) =>
    requestJson('/settings/default-model', { ...mutation('PUT', { profile_id }), signal }),
}
