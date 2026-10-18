import { onBeforeUnmount, onMounted, ref } from 'vue'
import { toolsApi } from '../api/tools'
import type { MCPServer } from '../types/tools'

export function useTools() {
  const servers = ref<MCPServer[]>([])
  const selected = ref<Record<string, string[]>>({})
  const loading = ref(false)
  const busy = ref('')
  const error = ref('')
  const feedback = ref('')
  let disposed = false
  let loadVersion = 0
  let listRequest: AbortController | undefined
  let actionRequest: AbortController | undefined

  async function load() {
    listRequest?.abort()
    listRequest = new AbortController()
    const version = ++loadVersion
    loading.value = true
    try {
      const result = await toolsApi.list(listRequest.signal)
      if (disposed || version !== loadVersion) return
      const previous = new Map(servers.value.map((server) => [server.id, server.revision]))
      selected.value = Object.fromEntries(
        result.items.map((item) => [
          item.id,
          previous.get(item.id) === item.revision
            ? [...(selected.value[item.id] ?? item.selected_tools)]
            : [...item.selected_tools],
        ]),
      )
      servers.value = result.items
    } catch (cause) {
      if (!disposed && version === loadVersion && !listRequest.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '无法读取 MCP 配置'
    } finally {
      if (!disposed && version === loadVersion) loading.value = false
    }
  }
  async function action(key: string, operation: (signal: AbortSignal) => Promise<string>) {
    if (disposed || busy.value) return
    const request = new AbortController()
    actionRequest = request
    busy.value = key
    error.value = feedback.value = ''
    try {
      const message = await operation(request.signal)
      if (!disposed && !request.signal.aborted) feedback.value = message
    } catch (cause) {
      if (!disposed)
        error.value = request.signal.aborted
          ? '已停止等待，服务状态可重新连接确认。'
          : cause instanceof Error
            ? cause.message
            : '操作失败'
    } finally {
      if (!disposed) {
        await load()
        busy.value = ''
      }
      if (actionRequest === request) actionRequest = undefined
    }
  }
  function cancel() {
    actionRequest?.abort()
  }
  onMounted(load)
  onBeforeUnmount(() => {
    disposed = true
    listRequest?.abort()
    actionRequest?.abort()
  })
  return { servers, selected, loading, busy, error, feedback, load, action, cancel }
}
