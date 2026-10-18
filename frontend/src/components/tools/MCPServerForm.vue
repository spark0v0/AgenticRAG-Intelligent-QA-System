<script setup lang="ts">
import { onBeforeUnmount, reactive, ref } from 'vue'
import { ElDialog } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import { ApiError } from '../../api/client'
import { toolsApi } from '../../api/tools'
import type { MCPServer, MCPSettings } from '../../types/tools'

const props = defineProps<{ server?: MCPServer }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const form = reactive<MCPSettings>({
  name: props.server?.name ?? '',
  transport: props.server?.transport ?? 'streamable_http',
  url: props.server?.url ?? '',
  command: props.server?.command ?? '',
  args: props.server?.args ?? [],
  env_names: props.server?.env_names ?? [],
  token_env: props.server?.token_env ?? '',
  timeout_seconds: props.server?.timeout_seconds ?? 15,
})
const args = ref(JSON.stringify(form.args, null, 2))
const envNames = ref(form.env_names.join(', '))
const pending = ref(false)
const error = ref('')
const errors = ref<Record<string, string>>({})
const controller = new AbortController()
let disposed = false
async function save() {
  if (pending.value) return
  error.value = ''
  errors.value = {}
  try {
    if (form.transport === 'stdio') {
      const parsed: unknown = JSON.parse(args.value)
      if (!Array.isArray(parsed) || !parsed.every((arg): arg is string => typeof arg === 'string'))
        throw new Error('启动参数需为 JSON 字符串数组，例如 ["server.py"]')
      form.args = parsed
      form.env_names = envNames.value
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
    }
    pending.value = true
    await toolsApi.save(form, props.server?.id, controller.signal)
    if (!disposed) emit('saved')
  } catch (cause) {
    if (disposed) return
    if (cause instanceof ApiError)
      errors.value = Object.fromEntries(cause.issues.map((issue) => [issue.field, issue.message]))
    error.value =
      cause instanceof SyntaxError
        ? '启动参数不是有效的 JSON 数组'
        : cause instanceof Error
          ? cause.message
          : '保存失败'
  } finally {
    if (!disposed) pending.value = false
  }
}
onBeforeUnmount(() => {
  disposed = true
  controller.abort()
})
</script>
<template>
  <ElDialog
    :model-value="true"
    :title="server ? '编辑 MCP 服务' : '添加 MCP 服务'"
    width="580px"
    :close-on-click-modal="false"
    :close-on-press-escape="!pending"
    :show-close="!pending"
    @close="emit('close')"
  >
    <form id="mcp-settings-form" class="mcp-form" @submit.prevent="save">
      <p class="mcp-hint">保存后连接服务，选择只读工具用于问答。密钥仅在后端环境变量中配置。</p>
      <p v-if="error" role="alert" class="inline-error">{{ error }}</p>
      <label
        >服务名称<input
          v-model="form.name"
          required
          maxlength="80"
          :disabled="pending"
          placeholder="例如：团队文档检索"
        /><small v-if="errors.name" class="inline-error">{{ errors.name }}</small></label
      >
      <label
        >连接方式<select v-model="form.transport" :disabled="pending">
          <option value="streamable_http">Streamable HTTP · 服务地址</option>
          <option value="stdio">stdio · 本地程序</option>
        </select></label
      >
      <template v-if="form.transport === 'streamable_http'">
        <label
          >服务地址<input
            v-model="form.url"
            type="url"
            required
            maxlength="500"
            :disabled="pending"
            placeholder="http://127.0.0.1:8001/mcp"
          /><small v-if="errors.url" class="inline-error">{{ errors.url }}</small></label
        >
        <label
          >Token 环境变量名（可选）<input
            v-model="form.token_env"
            maxlength="100"
            :disabled="pending"
            placeholder="例如：MY_MCP_TOKEN，勿填写密钥本身"
        /></label>
      </template>
      <template v-else>
        <label
          >可执行程序<input
            v-model="form.command"
            required
            maxlength="500"
            :disabled="pending"
            placeholder="例如：Python 的完整路径"
          /><small v-if="errors.command" class="inline-error">{{ errors.command }}</small></label
        >
        <label
          >启动参数（JSON 数组）<textarea
            v-model="args"
            rows="3"
            :disabled="pending"
            spellcheck="false"
            placeholder='["path/to/server.py"]'
          />
        </label>
        <label
          >传入的环境变量名（可选，逗号分隔）<input
            v-model="envNames"
            :disabled="pending"
            placeholder="例如：SERVICE_API_KEY"
        /></label>
        <p class="mcp-hint">连接时会启动该程序。使用已安装且可信的服务，凭据不要写入启动参数。</p>
      </template>
      <label
        >请求超时（秒）<input
          v-model.number="form.timeout_seconds"
          type="number"
          min="3"
          max="20"
          required
          :disabled="pending"
      /></label>
      <p v-if="server" class="mcp-hint">保存修改后停用旧工具，需要重新连接并选择。</p>
    </form>
    <template #footer
      ><button class="secondary-button" :disabled="pending" @click="emit('close')">取消</button
      ><button class="primary-button" type="submit" form="mcp-settings-form" :disabled="pending">
        {{ pending ? '保存中…' : '保存配置' }}
      </button></template
    >
  </ElDialog>
</template>
