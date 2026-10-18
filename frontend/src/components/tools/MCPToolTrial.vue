<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { ElDialog } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import { toolsApi } from '../../api/tools'
import type { MCPServer, MCPTool, ToolTrialResult } from '../../types/tools'
import type { Json } from '../../types'

const props = defineProps<{ server: MCPServer; tool: MCPTool }>()
const emit = defineEmits<{ close: []; executed: [] }>()
const argumentsText = ref('{}')
const pending = ref(false)
const error = ref('')
const result = ref<ToolTrialResult>()
let request: AbortController | undefined
let disposed = false
async function run() {
  if (pending.value) return
  error.value = ''
  result.value = undefined
  request = new AbortController()
  try {
    const args: Json = JSON.parse(argumentsText.value)
    if (!args || typeof args !== 'object' || Array.isArray(args))
      throw new Error('参数必须是 JSON 对象')
    pending.value = true
    const response = await toolsApi.call(props.server.id, props.tool.name, args, request.signal)
    if (!disposed && !request.signal.aborted) {
      result.value = response
      emit('executed')
    }
  } catch (cause) {
    if (!disposed)
      error.value = request?.signal.aborted
        ? '已停止等待本次调用；已发出的请求以服务实际执行结果为准。'
        : cause instanceof SyntaxError
          ? '参数不是有效的 JSON 对象'
          : cause instanceof Error
            ? cause.message
            : '试运行失败'
  } finally {
    if (!disposed) pending.value = false
  }
}
onBeforeUnmount(() => {
  disposed = true
  request?.abort()
})
</script>
<template>
  <ElDialog
    :model-value="true"
    title="工具试运行"
    width="640px"
    :close-on-click-modal="false"
    @close="emit('close')"
  >
    <div class="mcp-form">
      <strong>{{ server.name }} / {{ tool.name }}</strong>
      <p class="mcp-hint">{{ tool.description }}</p>
      <details class="schema-details" open>
        <summary>参数 Schema</summary>
        <pre>{{ JSON.stringify(tool.schema, null, 2) }}</pre>
      </details>
      <label
        >调用参数（JSON 对象）<textarea
          v-model="argumentsText"
          rows="5"
          :disabled="pending"
          spellcheck="false"
        />
      </label>
      <p class="mcp-hint">将实际调用一次工具，可能消耗服务额度；不会调用回答模型或自动重试。</p>
      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
      <div v-if="result" class="mcp-result" aria-live="polite">
        <strong
          >{{ result.status === 'success' ? '调用成功' : '调用失败' }} ·
          {{ result.metadata.latency_ms }} ms</strong
        >
        <p v-if="result.error">{{ result.error }}</p>
        <pre v-for="(doc, i) in result.documents" :key="i">{{ doc.content }}</pre>
        <p v-if="result.status === 'success' && !result.documents.length">
          工具返回为空，没有可展示的文本证据。
        </p>
      </div>
    </div>
    <template #footer
      ><button v-if="pending" class="secondary-button" @click="request?.abort()">停止</button
      ><button v-else class="secondary-button" @click="emit('close')">关闭</button
      ><button class="primary-button" :disabled="pending" @click="run">
        {{ pending ? '调用中…' : '执行查询' }}
      </button></template
    >
  </ElDialog>
</template>
