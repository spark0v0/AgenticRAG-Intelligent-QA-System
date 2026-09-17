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
  list: () => requestJson<ProviderList>('/settings/providers'),
  save: (body: ProviderSettings & { api_key: string; clear_key: boolean }, id?: string) =>
    requestJson<{ id: string }>(
      `/settings/providers${id ? `/${encodeURIComponent(id)}` : ''}`,
      mutation(id ? 'PUT' : 'POST', body),
    ),
  remove: (id: string) =>
    requestJson(`/settings/providers/${encodeURIComponent(id)}`, mutation('DELETE')),
  check: (id: string) =>
    requestJson<{ ok: boolean; message: string; models: string[] }>(
      `/settings/providers/${encodeURIComponent(id)}/check`,
      mutation('POST'),
    ),
  setDefault: (profile_id: string) =>
    requestJson('/settings/default-model', mutation('PUT', { profile_id })),
}
