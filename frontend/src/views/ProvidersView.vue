<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElSelect,
  ElOption,
  ElSwitch,
  ElMessageBox,
} from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/switch/style/css'
import 'element-plus/es/components/message-box/style/css'
import AppIcon from '../components/AppIcon.vue'
import { settingsApi } from '../api/settings'
import { useWorkbench } from '../stores/workbench'
import type { ProviderModel, ProviderRecord, ProviderSettings } from '../types'

const store = useWorkbench()
const providers = ref<ProviderRecord[]>([])
const storage = ref('')
const loading = ref(false)
const busy = ref('')
const error = ref('')
const feedback = ref('')
const open = ref(false)
const editing = ref<string>()
const discovered = ref<Record<string, string[]>>({})
const form = reactive<ProviderSettings & { api_key: string; clear_key: boolean }>({
  name: '',
  protocol: 'openai',
  base_url: '',
  timeout_seconds: 90,
  api_key: '',
  clear_key: false,
  models: [],
})
const fileProfiles = computed(
  () => store.system?.model_profiles.filter((p) => !p.id.startsWith('managed:')) ?? [],
)
const protocols = [
  { value: 'openai', label: 'OpenAI 兼容', url: 'https://api.openai.com/v1' },
  { value: 'deepseek', label: 'DeepSeek', url: 'https://api.deepseek.com' },
  { value: 'ollama', label: 'Ollama', url: 'http://localhost:11434' },
  { value: 'xinference', label: 'Xinference', url: 'http://localhost:9997/v1' },
] as const
const supportsStream = computed(() => ['openai', 'deepseek'].includes(form.protocol))
function model(name = ''): ProviderModel {
  return {
    model_name: name,
    label: name,
    supports_vision: false,
    supports_streaming: supportsStream.value,
    enabled: true,
    max_tokens: 4096,
  }
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await settingsApi.list()
    providers.value = response.items
    storage.value = response.credential_storage
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取配置失败'
  } finally {
    loading.value = false
  }
}
function edit(provider?: ProviderRecord) {
  editing.value = provider?.id
  Object.assign(
    form,
    provider
      ? {
          name: provider.name,
          protocol: provider.protocol,
          base_url: provider.base_url,
          timeout_seconds: provider.timeout_seconds,
          models: provider.models.map((m) => ({ ...m })),
        }
      : {
          name: '',
          protocol: 'openai',
          base_url: protocols[0].url,
          timeout_seconds: 90,
          models: [model()],
        },
  )
  form.api_key = ''
  form.clear_key = false
  error.value = ''
  open.value = true
}
function protocolChanged() {
  form.base_url = protocols.find((p) => p.value === form.protocol)!.url
  if (!supportsStream.value)
    form.models.forEach((m) => {
      m.supports_streaming = false
    })
}
async function save() {
  if (!form.name.trim() || !form.base_url.trim() || form.models.some((m) => !m.model_name.trim())) {
    error.value = '请填写供应商名称、服务地址及模型 ID'
    return
  }
  busy.value = 'save'
  error.value = ''
  try {
    await settingsApi.save(
      {
        ...form,
        name: form.name.trim(),
        models: form.models.map((m) => ({
          ...m,
          model_name: m.model_name.trim(),
          label: m.label.trim() || m.model_name.trim(),
        })),
      },
      editing.value,
    )
    form.api_key = ''
    open.value = false
    await load()
    await store.initialize()
    feedback.value = '配置已保存，模型选择已更新'
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    busy.value = ''
  }
}
async function check(provider: ProviderRecord) {
  busy.value = provider.id
  error.value = ''
  feedback.value = ''
  try {
    const result = await settingsApi.check(provider.id)
    discovered.value[provider.id] = result.models
    feedback.value = result.message
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '连接失败'
  } finally {
    busy.value = ''
  }
}
async function remove(provider: ProviderRecord) {
  try {
    await ElMessageBox.confirm(
      `移除「${provider.name}」及其本机密钥？历史回答保留，正在执行的请求继续使用原配置。`,
      '移除供应商',
      { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  busy.value = provider.id
  try {
    await settingsApi.remove(provider.id)
    await load()
    await store.initialize()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '移除失败'
  } finally {
    busy.value = ''
  }
}
async function setDefault(id: string) {
  busy.value = id
  try {
    await settingsApi.setDefault(id)
    await store.initialize()
    store.model = id
    feedback.value = '默认模型已更新'
  } catch (e) {
    error.value = e instanceof Error ? e.message : '更新失败'
  } finally {
    busy.value = ''
  }
}
function profileId(provider: ProviderRecord, item: ProviderModel) {
  return `managed:${provider.id}:${item.model_name}`
}
function addDiscovered(name: string) {
  if (!form.models.some((m) => m.model_name === name)) form.models.push(model(name))
}
onMounted(load)
</script>
<template>
  <main class="page-view providers-page">
    <div class="page-title">
      <div>
        <span class="eyebrow">CONNECTIONS</span>
        <h1>模型供应商<span class="heading-dot"></span></h1>
        <p>你的模型，你的工作空间。</p>
      </div>
      <button class="primary-button" @click="edit()">
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
            : '本机权限文件保存 · 非加密存储'
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
        :disabled="loading"
        @click="load"
      >
        <AppIcon name="refresh" :size="16" />
      </button>
    </div>
    <div v-if="loading && !providers.length" class="empty-page">正在读取供应商…</div>
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
                  ? '接口已连接'
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
              ><span v-if="!item.enabled">已停用</span>
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
              busy === provider.id ? '连接中…' : '检测连接 / 获取模型'
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
    <ElDialog
      v-model="open"
      :title="editing ? '编辑供应商' : '添加供应商'"
      width="680px"
      class="provider-dialog"
      :close-on-click-modal="false"
      :close-on-press-escape="!busy"
      :show-close="!busy"
      @closed="form.api_key = ''"
    >
      <ElForm label-position="top" @submit.prevent="save"
        ><div class="form-grid">
          <ElFormItem label="供应商名称"
            ><ElInput
              v-model="form.name"
              maxlength="80"
              placeholder="例如：我的 DeepSeek" /></ElFormItem
          ><ElFormItem label="接口协议"
            ><ElSelect v-model="form.protocol" @change="protocolChanged"
              ><ElOption
                v-for="p in protocols"
                :key="p.value"
                :label="p.label"
                :value="p.value" /></ElSelect
          ></ElFormItem>
        </div>
        <ElFormItem label="服务基础地址"
          ><ElInput v-model="form.base_url" placeholder="https://api.example.com/v1" /></ElFormItem
        ><ElFormItem label="API Key"
          ><ElInput
            v-model="form.api_key"
            type="password"
            autocomplete="new-password"
            :placeholder="editing ? '留空保留已有凭据' : '输入供应商 API Key'"
        /></ElFormItem>
        <div class="credential-options">
          <label v-if="editing"
            ><ElSwitch v-model="form.clear_key" :disabled="!!form.api_key" />清除已有凭据</label
          ><label
            >请求超时
            <ElInputNumber v-model="form.timeout_seconds" :min="5" :max="600" size="small" />
            秒</label
          >
        </div>
        <div class="section-heading form-model-heading">
          <h3>模型</h3>
          <button type="button" class="text-action" @click="form.models.push(model())">
            <AppIcon name="plus" :size="15" />添加模型
          </button>
        </div>
        <div v-if="editing && discovered[editing]?.length" class="discovered-picker">
          <ElSelect
            placeholder="从已发现的模型中添加"
            filterable
            :model-value="undefined"
            @change="addDiscovered"
            ><ElOption v-for="name in discovered[editing]" :key="name" :label="name" :value="name"
          /></ElSelect>
        </div>
        <div v-for="(item, index) in form.models" :key="index" class="model-editor">
          <div class="model-fields">
            <ElInput
              v-model="item.model_name"
              :aria-label="`模型 ID ${index + 1}`"
              placeholder="模型 ID，如 deepseek-chat"
            /><ElInput
              v-model="item.label"
              :aria-label="`显示名称 ${index + 1}`"
              placeholder="显示名称"
            /><button
              type="button"
              class="icon-button"
              :aria-label="`移除模型 ${index + 1}`"
              title="移除此模型"
              @click="form.models.splice(index, 1)"
            >
              <AppIcon name="close" :size="16" />
            </button>
          </div>
          <div class="model-switches">
            <label><ElSwitch v-model="item.enabled" size="small" />启用</label
            ><label
              ><ElSwitch
                v-model="item.supports_streaming"
                size="small"
                :disabled="!supportsStream"
              />流式</label
            ><label><ElSwitch v-model="item.supports_vision" size="small" />图片输入</label
            ><label
              >最大输出
              <ElInputNumber v-model="item.max_tokens" :min="64" :max="65536" size="small"
            /></label>
          </div>
        </div>
        <p class="field-note">能力开关按供应商文档配置；连接检查仅访问模型列表，不发送问答。</p>
        <p v-if="error" class="inline-error" role="alert">{{ error }}</p> </ElForm
      ><template #footer
        ><button class="secondary-button" :disabled="!!busy" @click="open = false">取消</button
        ><button class="primary-button" :disabled="!!busy" @click="save">
          <AppIcon name="check" :size="16" />{{ busy === 'save' ? '保存中…' : '保存配置' }}
        </button></template
      >
    </ElDialog>
  </main>
</template>
