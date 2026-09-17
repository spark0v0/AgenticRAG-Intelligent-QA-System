<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElSelect,
  ElOption,
  ElSwitch,
} from 'element-plus'
import type { FormInstance, FormRules, FormItemRule } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/switch/style/css'
import { ApiError } from '../../api/client'
import { settingsApi } from '../../api/settings'
import type { ProviderModel, ProviderRecord, ProviderSettings } from '../../types'
import AppIcon from '../AppIcon.vue'
import ProviderModelEditor from './ProviderModelEditor.vue'

const props = defineProps<{ provider?: ProviderRecord; discovered: string[] }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const formRef = ref<FormInstance>()
const summary = ref<HTMLElement>()
const pending = ref(false)
const error = ref('')
const fieldErrors = ref<Record<string, string>>({})
const invalidFields = ref<{ field: string; message: string }[]>([])
const controller = new AbortController()
let disposed = false
const protocols = [
  { value: 'openai', label: 'OpenAI 兼容', url: 'https://api.openai.com/v1' },
  { value: 'deepseek', label: 'DeepSeek', url: 'https://api.deepseek.com' },
  { value: 'ollama', label: 'Ollama', url: 'http://localhost:11434' },
  { value: 'xinference', label: 'Xinference', url: 'http://localhost:9997/v1' },
] as const
const form = reactive<ProviderSettings & { api_key: string; clear_key: boolean }>({
  name: props.provider?.name ?? '',
  protocol: props.provider?.protocol ?? 'openai',
  base_url: props.provider?.base_url ?? protocols[0].url,
  timeout_seconds: props.provider?.timeout_seconds ?? 90,
  api_key: '',
  clear_key: false,
  models: props.provider?.models.map((model) => ({ ...model })) ?? [newModel()],
})
const streaming = computed(() => ['openai', 'deepseek'].includes(form.protocol))
function newModel(name = ''): ProviderModel {
  return {
    model_name: name,
    label: name,
    enabled: true,
    supports_streaming: true,
    supports_vision: false,
    max_tokens: 4096,
  }
}
const rules: FormRules = {
  name: [{ required: true, whitespace: true, message: '请填写供应商名称', trigger: 'blur' }],
  base_url: [
    {
      validator: (_rule, value: string, callback) => {
        try {
          const url = new URL(value.trim())
          if (
            !['http:', 'https:'].includes(url.protocol) ||
            !url.hostname ||
            url.username ||
            url.password ||
            url.search ||
            url.hash
          )
            throw new Error('请填写不含凭据、查询参数或片段的 HTTP(S) 地址')
          if (
            url.protocol === 'http:' &&
            !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
          )
            throw new Error('远程服务需要 HTTPS；本机服务可使用 HTTP')
          if (value.length > 500) throw new Error('服务地址不能超过 500 个字符')
          callback()
        } catch (cause) {
          callback(
            new Error(
              cause instanceof TypeError
                ? '请填写完整的服务地址，如 https://api.example.com/v1'
                : (cause as Error).message,
            ),
          )
        }
      },
      trigger: 'blur',
    },
  ],
  api_key: [{ max: 4096, message: '凭据不能超过 4096 个字符', trigger: 'blur' }],
  timeout_seconds: [
    {
      type: 'integer',
      required: true,
      min: 5,
      max: 600,
      message: '请输入 5～600 秒的整数',
      trigger: 'change',
    },
  ],
}
const idRules: FormItemRule[] = [
  {
    validator: (_rule, value: string, callback) => {
      const id = value.trim()
      callback(
        !id
          ? new Error('请填写模型 ID')
          : /\s/.test(id)
            ? new Error('模型 ID 不能包含空格')
            : form.models.filter((m) => m.model_name.trim() === id).length > 1
              ? new Error('同一供应商中模型 ID 不可重复')
              : undefined,
      )
    },
    trigger: 'blur',
  },
]
watch(
  () => form.api_key,
  (value) => {
    if (value) form.clear_key = false
  },
)
function protocolChanged() {
  form.base_url = protocols.find((p) => p.value === form.protocol)!.url
  if (!streaming.value)
    form.models.forEach((m) => {
      m.supports_streaming = false
    })
}
function addModel(name = '') {
  if (form.models.length >= 100 || (name && form.models.some((m) => m.model_name === name))) return
  form.models.push({ ...newModel(name), supports_streaming: streaming.value })
}
function focusField(field: string) {
  formRef.value?.scrollToField(field)
  const context = formRef.value?.fields.find((item) => item.propString === field)
  context?.$el?.querySelector<HTMLInputElement>('input')?.focus()
}
async function showError() {
  await nextTick()
  summary.value?.focus()
}
async function save() {
  if (pending.value) return
  error.value = ''
  fieldErrors.value = {}
  invalidFields.value = []
  pending.value = true
  const valid = await formRef.value
    ?.validate((ok, fields) => {
      if (!ok)
        invalidFields.value = Object.entries(fields ?? {}).map(([field, issues]) => ({
          field,
          message: issues[0]?.message ?? '请检查此字段',
        }))
    })
    .catch(() => false)
  if (!valid) {
    pending.value = false
    error.value = '请修正以下内容后保存'
    await showError()
    return
  }
  try {
    await settingsApi.save(
      {
        ...form,
        name: form.name.trim(),
        base_url: form.base_url.trim(),
        models: form.models.map((m) => ({
          ...m,
          model_name: m.model_name.trim(),
          label: m.label.trim() || m.model_name.trim(),
        })),
      },
      props.provider?.id,
      controller.signal,
    )
    if (!disposed) {
      form.api_key = ''
      emit('saved')
    }
  } catch (cause) {
    if (disposed) return
    if (cause instanceof ApiError) {
      invalidFields.value = cause.issues.filter((item) => !!item.field)
      fieldErrors.value = Object.fromEntries(
        invalidFields.value.map((item) => [item.field, item.message]),
      )
    }
    error.value = cause instanceof Error ? cause.message : '保存失败，请重试'
    if (!(cause instanceof ApiError))
      error.value = '未能确认保存结果，请检查连接并刷新供应商列表；表单内容已保留。'
    await showError()
  } finally {
    if (!disposed) pending.value = false
  }
}
onBeforeUnmount(() => {
  disposed = true
  controller.abort()
  form.api_key = ''
})
</script>
<template>
  <ElDialog
    :model-value="true"
    :title="provider ? '编辑供应商' : '添加供应商'"
    width="680px"
    class="provider-dialog"
    :close-on-click-modal="false"
    :close-on-press-escape="!pending"
    :show-close="!pending"
    @update:model-value="!pending && emit('close')"
  >
    <ElForm
      ref="formRef"
      :model="form"
      :rules="rules"
      :disabled="pending"
      label-position="top"
      @submit.prevent="save"
    >
      <div
        v-if="error"
        ref="summary"
        class="form-error-summary inline-error"
        role="alert"
        tabindex="-1"
      >
        <strong>{{ error }}</strong>
        <ul v-if="invalidFields.length">
          <li v-for="item in invalidFields" :key="item.field">
            <button type="button" @click="focusField(item.field)">{{ item.message }}</button>
          </li>
        </ul>
      </div>
      <div class="form-grid">
        <ElFormItem label="供应商名称" prop="name" :error="fieldErrors.name"
          ><ElInput v-model="form.name" maxlength="80" placeholder="例如：我的 DeepSeek"
        /></ElFormItem>
        <ElFormItem label="接口协议" prop="protocol" :error="fieldErrors.protocol"
          ><ElSelect v-model="form.protocol" @change="protocolChanged"
            ><ElOption
              v-for="p in protocols"
              :key="p.value"
              :label="p.label"
              :value="p.value" /></ElSelect
        ></ElFormItem>
      </div>
      <ElFormItem label="服务基础地址" prop="base_url" :error="fieldErrors.base_url"
        ><ElInput v-model="form.base_url" placeholder="https://api.example.com/v1"
      /></ElFormItem>
      <ElFormItem label="API Key" prop="api_key" :error="fieldErrors.api_key"
        ><ElInput
          v-model="form.api_key"
          type="password"
          autocomplete="new-password"
          :disabled="form.clear_key"
          :placeholder="provider ? '留空保留已有凭据' : '输入供应商 API Key'"
      /></ElFormItem>
      <div class="credential-options">
        <label v-if="provider"
          ><ElSwitch v-model="form.clear_key" :disabled="!!form.api_key" />清除已有凭据</label
        >
        <ElFormItem
          label="请求超时（秒）"
          prop="timeout_seconds"
          :error="fieldErrors.timeout_seconds"
          ><ElInputNumber v-model="form.timeout_seconds" :min="5" :max="600"
        /></ElFormItem>
      </div>
      <div class="section-heading form-model-heading">
        <h3>
          可用模型 <span class="muted">{{ form.models.length }}</span>
        </h3>
        <button
          type="button"
          class="text-action"
          :disabled="pending || form.models.length >= 100"
          @click="addModel()"
        >
          <AppIcon name="plus" :size="16" />添加模型
        </button>
      </div>
      <div v-if="discovered.length" class="discovered-picker">
        <ElSelect
          placeholder="从已发现的模型中添加"
          filterable
          :model-value="undefined"
          @change="addModel"
          ><ElOption v-for="name in discovered" :key="name" :label="name" :value="name"
        /></ElSelect>
      </div>
      <ProviderModelEditor
        v-for="(_, index) in form.models"
        :key="index"
        v-model="form.models[index]!"
        :index="index"
        :streaming="streaming"
        :pending="pending"
        :errors="fieldErrors"
        :id-rules="idRules"
        @remove="!pending && form.models.splice(index, 1)"
      />
      <p v-if="!form.models.length" class="notice">
        尚未添加模型。供应商可保存，添加模型后才能用于问答。
      </p>
      <p class="field-note">
        能力开关以供应商文档为准；连接检查仅访问模型列表，不代表生成请求成功。
      </p>
    </ElForm>
    <template #footer
      ><button class="secondary-button" :disabled="pending" @click="emit('close')">取消</button
      ><button class="primary-button" :disabled="pending" @click="save">
        <AppIcon name="check" :size="16" />{{ pending ? '保存中…' : '保存配置' }}
      </button></template
    >
  </ElDialog>
</template>
