import { requestJson } from './client'
import type { Json } from '../types'
import type { MCPServer, MCPSettings, ToolTrialResult } from '../types/tools'

function send<T>(path: string, method: string, body: unknown, signal?: AbortSignal) {
  return requestJson<T>(`/settings/mcp${path}`, {
    method,
    signal,
    headers: { 'Content-Type': 'application/json', 'X-Workbench-Request': '1' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}
const path = (id: string) => `/${encodeURIComponent(id)}`
export const toolsApi = {
  list: (signal?: AbortSignal) => requestJson<{ items: MCPServer[] }>('/settings/mcp', { signal }),
  save: (body: MCPSettings, id?: string, signal?: AbortSignal) =>
    send<{ id: string }>(id ? path(id) : '', id ? 'PUT' : 'POST', body, signal),
  remove: (id: string, signal?: AbortSignal) =>
    send<{ removed: boolean }>(path(id), 'DELETE', undefined, signal),
  discover: (id: string, signal?: AbortSignal) =>
    send<{ ok: boolean; message: string }>(`${path(id)}/discover`, 'POST', undefined, signal),
  activate: (id: string, enabled: boolean, selected_tools: string[], signal?: AbortSignal) =>
    send<{ updated: boolean }>(path(id), 'PATCH', { enabled, selected_tools }, signal),
  call: (id: string, name: string, args: Record<string, Json>, signal?: AbortSignal) =>
    send<ToolTrialResult>(`${path(id)}/call`, 'POST', { name, arguments: args }, signal),
}
