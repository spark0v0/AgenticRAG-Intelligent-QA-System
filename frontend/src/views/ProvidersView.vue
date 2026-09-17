<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'
import AppIcon from '../components/AppIcon.vue'
import ProviderForm from '../components/providers/ProviderForm.vue'
import { settingsApi } from '../api/settings'
import { useWorkbench } from '../stores/workbench'
import type { ProviderModel, ProviderRecord } from '../types'
const store = useWorkbench()
const providers = ref<ProviderRecord[]>([])
const storage = ref('')
const loading = ref(false)
const busy = ref('')
const error = ref('')
const feedback = ref('')
const open = ref(false)
const editing = ref<ProviderRecord>()
const discovered = ref<Record<string, string[]>>({})
const fileProfiles = computed(
  () => store.system?.model_profiles.filter((p) => !p.id.startsWith('managed:')) ?? [],
)
const protocols = [
  { value: 'openai', label: 'OpenAI 兼容' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'xinference', label: 'Xinference' },
]
const actionController = new AbortController()
let listController: AbortController | undefined
let listVersion = 0
let disposed = false
async function load() {
  listController?.abort()
  listController = new AbortController()
  const version = ++listVersion
  loading.value = true
  try {
    const response = await settingsApi.list(listController.signal)
    if (disposed || version !== listVersion) return
    providers.value = response.items
    storage.value = response.credential_storage
  } catch (cause) {
    if (
      !disposed &&
      version === listVersion &&
      !(cause instanceof DOMException && cause.name === 'AbortError')
    )
      error.value = cause instanceof Error ? cause.message : '读取配置失败'
  } finally {
    if (!disposed && version === listVersion) loading.value = false
  }
}
function edit(provider?: ProviderRecord) {
  if (busy.value) return
  editing.value = provider
  error.value = ''
  feedback.value = ''
  open.value = true
}
async function saved() {
  open.value = false
  feedback.value = '配置已保存'
  await load()
  if (!disposed) await store.initialize()
}
async function action(id: string, operation: () => Promise<void>) {
  if (busy.value || disposed) return
  busy.value = id
  error.value = ''
  feedback.value = ''
  try {
    await operation()
  } catch (cause) {
    if (!disposed) error.value = cause instanceof Error ? cause.message : '操作失败，请重试'
  } finally {
    if (!disposed) busy.value = ''
  }
}
async function check(provider: ProviderRecord) {
  await action(`check:${provider.id}`, async () => {
    const result = await settingsApi.check(provider.id, actionController.signal)
    if (disposed) return
    discovered.value[provider.id] = result.ok ? result.models : []
    if (result.ok) feedback.value = result.message
    else error.value = result.message
    await load()
  })
}
async function remove(provider: ProviderRecord) {
  if (busy.value) return
  try {
    await ElMessageBox.confirm(
      `移除「${provider.name}」及其本机密钥？历史回答保留，正在执行的请求继续使用原配置。`,
      '移除供应商',
      { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await action(`remove:${provider.id}`, async () => {
    await settingsApi.remove(provider.id, actionController.signal)
    if (disposed) return
    feedback.value = '供应商已移除，历史回答已保留'
    await load()
    if (!disposed) await store.initialize()
  })
}
async function setDefault(id: string) {
  await action(id, async () => {
    await settingsApi.setDefault(id, actionController.signal)
    if (disposed) return
    await store.initialize()
    if (disposed) return
    store.model = id
    feedback.value = '默认模型已更新'
  })
}
function profileId(provider: ProviderRecord, item: ProviderModel) {
  return `managed:${provider.id}:${item.model_name}`
}
function generationVerified(provider: ProviderRecord, item: ProviderModel) {
  return (
    store.system?.model_profiles.find((profile) => profile.id === profileId(provider, item))
      ?.connection_verified === true
  )
}
function refresh() {
  error.value = ''
  feedback.value = ''
  void load()
}
onMounted(load)
onBeforeUnmount(() => {
  disposed = true
  listVersion++
  listController?.abort()
  actionController.abort()
})
</script>
<template>
  <main class="page-view providers-page">
    <div class="page-title">
      <div>
        <h1>模型供应商</h1>
        <p>管理模型连接与可用能力。</p>
      </div>
      <button class="primary-button" :disabled="!!busy" @click="edit()">
        <AppIcon name="plus" :size="17" />添加供应商
      </button>
    </div>
    <div class="security-strip">
      <AppIcon name="shield" :size="20" />
      <div>
        <strong>凭据保存在本机后端</strong
        ><span>{{
          storage === 'windows-dpapi'
            ? 'Windows 用户级加密 · 不回传浏览器'
            : storage
              ? '本机权限文件保存 · 非加密存储'
              : '正在读取存储状态'
        }}</span>
      </div>
      <span class="subtle-badge">LOCAL</span>
    </div>
    <p v-if="error && !open" class="inline-error" role="alert">{{ error }}</p>
    <p v-if="feedback" class="feedback-line" role="status">
      <AppIcon name="check" :size="16" />{{ feedback }}
    </p>
    <div class="section-heading">
      <h2>
        我的供应商 <span>{{ providers.length }}</span>
      </h2>
      <button
        class="icon-button"
        title="刷新供应商"
        aria-label="刷新供应商"
        :disabled="loading || !!busy"
        @click="refresh"
      >
        <AppIcon name="refresh" :size="16" />
      </button>
    </div>
    <div v-if="loading && !providers.length" class="empty-page">正在读取供应商…</div>
    <div v-else-if="error && !providers.length" class="provider-empty">
      <h3>供应商列表暂不可用</h3>
      <button class="secondary-button" @click="refresh">
        <AppIcon name="refresh" :size="16" />重新读取
      </button>
    </div>
    <div v-else-if="!providers.length" class="provider-empty">
      <AppIcon name="server" :size="32" />
      <h3>连接第一个模型供应商</h3>
      <p>OpenAI 兼容服务、DeepSeek 或本机模型</p>
      <button class="secondary-button" @click="edit()">
        <AppIcon name="plus" :size="16" />添加供应商
      </button>
    </div>
    <div class="providers-list">
      <article v-for="provider in providers" :key="provider.id" class="provider-item">
        <header class="provider-heading">
          <span class="provider-avatar" :class="provider.protocol"
            ><AppIcon name="server" :size="22"
          /></span>
          <div>
            <h3>
              {{ provider.name
              }}<span class="protocol-label">{{
                protocols.find((p) => p.value === provider.protocol)?.label
              }}</span>
            </h3>
            <span class="provider-endpoint">{{ provider.base_url }}</span>
          </div>
          <div class="provider-actions">
            <span
              class="status-badge"
              :class="{ ready: provider.check_ok, failed: provider.check_ok === false }"
              >{{
                provider.check_ok === true
                  ? '模型列表已连通'
                  : provider.check_ok === false
                    ? '连接失败'
                    : '尚未验证'
              }}</span
            ><button
              class="icon-button"
              :disabled="!!busy"
              :aria-label="`编辑 ${provider.name}`"
              title="编辑供应商"
              @click="edit(provider)"
            >
              <AppIcon name="edit" :size="17" /></button
            ><button
              class="icon-button danger-button"
              :disabled="!!busy"
              :aria-label="`移除 ${provider.name}`"
              title="移除供应商"
              @click="remove(provider)"
            >
              <AppIcon name="trash" :size="17" />
            </button>
          </div>
        </header>
        <div class="provider-models">
          <div v-for="item in provider.models" :key="item.model_name" class="provider-model-row">
            <span class="model-avatar"><AppIcon name="spark" :size="17" /></span>
            <div class="model-name">
              <strong>{{ item.label }}</strong
              ><code>{{ item.model_name }}</code>
            </div>
            <div class="capability-tags">
              <span>{{ item.supports_streaming ? '流式输出' : '完整结果' }}</span
              ><span v-if="item.supports_vision">图片输入</span
              ><span v-if="!item.enabled">已停用</span
              ><span :class="{ verified: generationVerified(provider, item) }">{{
                generationVerified(provider, item) ? '生成已验证' : '生成未验证'
              }}</span>
            </div>
            <span
              v-if="store.system?.default_model_profile === profileId(provider, item)"
              class="default-label"
              ><AppIcon name="check" :size="14" />默认</span
            ><button
              v-else
              class="text-action"
              :disabled="!item.enabled || !!busy"
              @click="setDefault(profileId(provider, item))"
            >
              设为默认
            </button>
          </div>
          <p v-if="!provider.models.length" class="empty-hint">尚未添加模型</p>
        </div>
        <footer class="provider-footer">
          <span
            ><AppIcon name="key" :size="14" />{{ provider.has_key ? '凭据已保存' : '未设置凭据'
            }}<span class="separator">/</span>超时 {{ provider.timeout_seconds }}s</span
          ><button class="secondary-button compact" :disabled="!!busy" @click="check(provider)">
            <AppIcon name="pulse" :size="15" />{{
              busy === `check:${provider.id}` ? '连接中…' : '检测连接 / 获取模型'
            }}
          </button>
        </footer>
        <div v-if="discovered[provider.id]?.length" class="discovery-result">
          发现 {{ discovered[provider.id]!.length }} 个模型<button
            class="text-action"
            @click="edit(provider)"
          >
            选择并添加<AppIcon name="right" :size="13" />
          </button>
        </div>
        <p v-if="provider.check_message" class="provider-check-note">
          {{ provider.check_message }}
        </p>
      </article>
    </div>
    <section v-if="fileProfiles.length" class="settings-section inherited-section">
      <div class="section-heading">
        <h2>文件配置</h2>
        <span class="subtle-badge">兼容现有 YAML · 只读</span>
      </div>
      <div v-for="profile in fileProfiles" :key="profile.id" class="inherited-row">
        <AppIcon name="code" :size="19" />
        <div>
          <strong>{{ profile.label }}</strong
          ><small>{{ profile.provider }} · {{ profile.model_name }}</small>
        </div>
        <span class="status-badge" :class="{ ready: profile.configured }">{{
          profile.configured ? '已配置' : '未配置'
        }}</span
        ><span v-if="profile.id === store.system?.default_model_profile" class="default-label"
          >默认</span
        ><button
          v-else
          class="text-action"
          :disabled="!profile.configured || !!busy"
          @click="setDefault(profile.id)"
        >
          设为默认
        </button>
      </div>
    </section>
    <ProviderForm
      v-if="open"
      :provider="editing"
      :discovered="editing ? (discovered[editing.id] ?? []) : []"
      @close="open = false"
      @saved="saved"
    />
  </main>
</template>
