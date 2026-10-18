<script setup lang="ts">
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'
import AppIcon from '../AppIcon.vue'
import MCPServerForm from './MCPServerForm.vue'
import MCPToolTrial from './MCPToolTrial.vue'
import { toolsApi } from '../../api/tools'
import { useTools } from '../../composables/useTools'
import type { MCPServer, MCPTool } from '../../types/tools'

const { servers, selected, loading, busy, error, feedback, load, action, cancel } = useTools()
const formOpen = ref(false)
const editing = ref<MCPServer>()
const trial = ref<{ server: MCPServer; tool: MCPTool }>()
const statusNames: Record<string, string> = {
  success: '成功',
  error: '失败',
  timeout: '超时',
  cancelled: '已取消',
}
function edit(server?: MCPServer) {
  editing.value = server
  formOpen.value = true
}
async function saved() {
  formOpen.value = false
  feedback.value = '配置已保存，请连接服务发现工具。'
  await load()
}
async function discover(server: MCPServer) {
  await action(`discover:${server.id}`, async (signal) => {
    const result = await toolsApi.discover(server.id, signal)
    if (!result.ok) throw new Error(`${server.name}：${result.message}`)
    return `${server.name}：${result.message}`
  })
}
async function activate(server: MCPServer, enabled: boolean) {
  await action(`activate:${server.id}`, async (signal) => {
    await toolsApi.activate(server.id, enabled, selected.value[server.id] ?? [], signal)
    return enabled
      ? `${server.name}：所选工具已可用于自动范围的检索问答。`
      : `${server.name}：已停用，后续问答不再选择此服务。`
  })
}
async function remove(server: MCPServer) {
  try {
    await ElMessageBox.confirm(
      `删除「${server.name}」的连接配置及工具列表？历史回答和执行记录会保留。`,
      '删除 MCP 服务',
      { confirmButtonText: '删除配置', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await action(`remove:${server.id}`, async (signal) => {
    await toolsApi.remove(server.id, signal)
    return `已删除 ${server.name} 的连接配置。`
  })
}
function date(value: number) {
  return new Date(value * 1000).toLocaleString('zh-CN')
}
function closeTrial() {
  trial.value = undefined
  void load()
}
function alreadyApplied(server: MCPServer) {
  const draft = selected.value[server.id] ?? []
  return (
    server.enabled &&
    draft.length === server.selected_tools.length &&
    draft.every((name) => server.selected_tools.includes(name))
  )
}
</script>
<template>
  <section class="mcp-services" aria-labelledby="mcp-heading">
    <div class="mcp-section-heading">
      <div>
        <h2 id="mcp-heading">MCP 服务</h2>
        <p>连接外部数据源，选择查询工具，先试运行再用于问答。</p>
      </div>
      <button class="primary-button" :disabled="!!busy || loading" @click="edit()">
        <AppIcon name="plus" :size="16" />添加服务
      </button>
    </div>
    <p class="mcp-hint mcp-scope-note">
      启用后，在问答中选择「自动」范围与检索或深度模式。外部工具需要支持 Function Calling
      的模型；选定知识库或联网范围时仍只使用对应资料。
    </p>
    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <p v-if="feedback" class="mcp-feedback" role="status">{{ feedback }}</p>
    <p v-if="busy.startsWith('discover:')" class="mcp-feedback" role="status">
      正在连接并读取工具列表…<button class="secondary-button compact" @click="cancel">
        取消连接
      </button>
    </p>
    <div v-if="loading && !servers.length" class="mcp-empty" aria-busy="true">
      正在读取服务配置…
    </div>
    <div v-else-if="!servers.length" class="mcp-empty">
      <AppIcon name="layers" :size="28" />
      <div>
        <strong>连接你的第一个工具服务</strong>
        <p>支持 Streamable HTTP 和本地 stdio；保存配置不会立即调用工具。</p>
      </div>
      <button v-if="error" class="secondary-button" @click="load">重新加载</button>
    </div>
    <article
      v-for="server in servers"
      :key="server.id"
      class="mcp-service"
      :aria-busy="busy.endsWith(server.id)"
    >
      <header class="mcp-service-heading">
        <div class="mcp-service-name">
          <AppIcon name="layers" :size="20" />
          <h3>{{ server.name }}</h3>
          <span class="protocol-badge">{{
            server.transport === 'stdio' ? 'stdio' : 'Streamable HTTP'
          }}</span
          ><span class="subtle-badge">{{
            server.enabled ? `${server.selected_tools.length} 个工具已启用` : '未用于问答'
          }}</span>
        </div>
        <div class="mcp-actions">
          <button class="secondary-button compact" :disabled="!!busy" @click="edit(server)">
            编辑</button
          ><button class="secondary-button compact" :disabled="!!busy" @click="remove(server)">
            删除
          </button>
        </div>
      </header>
      <div class="mcp-connection">
        <code>{{ server.transport === 'stdio' ? server.command : server.url }}</code
        ><span :class="{ 'inline-error': server.check_ok === false }">{{
          server.check_ok === null ? '尚未连接' : server.check_ok ? '连接已验证' : '连接失败'
        }}</span
        ><small v-if="server.checked_at">{{ date(server.checked_at) }}</small>
      </div>
      <p v-if="server.check_message" class="mcp-hint">
        {{ server.enabled ? '所选工具已用于问答；可调整选择后重新应用。' : server.check_message }}
      </p>
      <div v-if="server.tools.length" class="mcp-discovered">
        <div v-for="tool in server.tools" :key="tool.name" class="mcp-tool-row">
          <label class="mcp-tool-choice"
            ><input
              v-model="selected[server.id]"
              type="checkbox"
              :value="tool.name"
              :disabled="!!busy || !tool.read_only"
            /><span
              ><strong>{{ tool.name }}</strong
              ><small>{{ tool.description }}</small
              ><small v-if="!tool.read_only">未声明只读，暂不支持在工作台调用。</small></span
            ></label
          ><button
            class="secondary-button compact"
            :disabled="!!busy || !tool.read_only"
            @click="trial = { server, tool }"
          >
            试运行
          </button>
        </div>
      </div>
      <footer class="mcp-service-footer">
        <div class="mcp-call-status">
          <span v-if="server.last_call"
            >最近调用：{{ server.last_call.tool }} ·
            {{ statusNames[server.last_call.status] || server.last_call.status
            }}<small>{{ date(server.last_call.at) }}</small></span
          ><span v-else>尚无调用记录</span>
        </div>
        <div class="mcp-actions">
          <button class="secondary-button compact" :disabled="!!busy" @click="discover(server)">
            {{
              busy === `discover:${server.id}`
                ? '连接中…'
                : server.check_ok
                  ? '重新发现'
                  : '连接并发现'
            }}</button
          ><button
            v-if="server.enabled"
            class="secondary-button compact"
            :disabled="!!busy"
            @click="activate(server, false)"
          >
            停用</button
          ><button
            v-if="server.check_ok && server.tools.length"
            class="primary-button compact"
            :disabled="
              !!busy ||
              !selected[server.id]?.length ||
              (selected[server.id]?.length ?? 0) > 16 ||
              alreadyApplied(server)
            "
            @click="activate(server, true)"
          >
            {{ alreadyApplied(server) ? '已应用到问答' : '应用到问答' }}
          </button>
        </div>
      </footer>
    </article>
    <p v-if="servers.length" class="mcp-hint">
      每个服务最多启用 16
      个只读工具。重新发现会停用旧选择，请核对最新工具后再应用。只读声明由服务提供，请仅接入可信来源。
    </p>
    <MCPServerForm v-if="formOpen" :server="editing" @close="formOpen = false" @saved="saved" />
    <MCPToolTrial v-if="trial" :server="trial.server" :tool="trial.tool" @close="closeTrial" />
  </section>
</template>
