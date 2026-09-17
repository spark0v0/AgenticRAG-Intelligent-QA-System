<script setup lang="ts">
import { ElFormItem, ElInput, ElInputNumber, ElSwitch } from 'element-plus'
import type { FormItemRule } from 'element-plus'
import type { ProviderModel } from '../../types'
import AppIcon from '../AppIcon.vue'
const item = defineModel<ProviderModel>({ required: true })
defineProps<{
  index: number
  streaming: boolean
  pending: boolean
  errors: Record<string, string>
  idRules: FormItemRule[]
}>()
defineEmits<{ remove: [] }>()
</script>
<template>
  <div class="model-editor">
    <div class="model-fields">
      <ElFormItem
        label="模型 ID"
        :prop="`models.${index}.model_name`"
        :rules="idRules"
        :error="errors[`models.${index}.model_name`]"
      >
        <ElInput
          v-model="item.model_name"
          :aria-label="`模型 ID ${index + 1}`"
          maxlength="160"
          placeholder="如 deepseek-chat"
        />
      </ElFormItem>
      <ElFormItem
        label="显示名称"
        :prop="`models.${index}.label`"
        :error="errors[`models.${index}.label`]"
      >
        <ElInput
          v-model="item.label"
          :aria-label="`显示名称 ${index + 1}`"
          maxlength="80"
          placeholder="默认使用模型 ID"
        />
      </ElFormItem>
      <button
        type="button"
        class="icon-button model-remove"
        :aria-label="`移除模型 ${index + 1}`"
        title="移除此模型"
        :disabled="pending"
        @click="$emit('remove')"
      >
        <AppIcon name="trash" :size="17" />
      </button>
    </div>
    <div class="model-switches">
      <label><ElSwitch v-model="item.enabled" />启用</label>
      <label><ElSwitch v-model="item.supports_streaming" :disabled="!streaming" />流式</label>
      <label><ElSwitch v-model="item.supports_vision" />图片输入</label>
      <ElFormItem
        label="最大输出"
        :prop="`models.${index}.max_tokens`"
        :rules="[
          {
            type: 'integer',
            required: true,
            min: 64,
            max: 65536,
            message: '请输入 64～65536 的整数',
            trigger: 'change',
          },
        ]"
        :error="errors[`models.${index}.max_tokens`]"
      >
        <ElInputNumber
          v-model="item.max_tokens"
          :min="64"
          :max="65536"
          :aria-label="`最大输出 ${index + 1}`"
        />
      </ElFormItem>
    </div>
  </div>
</template>
