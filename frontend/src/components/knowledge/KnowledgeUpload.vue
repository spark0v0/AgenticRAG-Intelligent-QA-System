<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from '../AppIcon.vue'
import type { UploadLimits } from '../../types/knowledge'
const props = defineProps<{ limits: UploadLimits; busy: boolean }>()
const emit = defineEmits<{ upload: [files: File[]] }>()
const error = ref('')
const input = ref<HTMLInputElement>()
const dragging = ref(false)
function choose(files: File[]) {
  error.value = ''
  if (props.busy || !files.length) return
  if (files.length > props.limits.files) error.value = `每次最多选择 ${props.limits.files} 个文件`
  else if (
    files.some(
      (f) => !props.limits.extensions.includes(`.${f.name.split('.').pop()?.toLowerCase()}`),
    )
  )
    error.value = '仅支持 TXT、Markdown 和文本型 PDF'
  else if (files.some((f) => !f.size || f.size > props.limits.file_bytes))
    error.value = '文件不能为空，且单文件不得超过 10 MiB'
  else if (files.reduce((sum, f) => sum + f.size + 1024, 0) > props.limits.request_bytes)
    error.value = '单次请求不得超过 32 MiB，请减少文件数量'
  else emit('upload', files)
}
function onChange(event: Event) {
  const target = event.target as HTMLInputElement
  choose(Array.from(target.files || []))
  target.value = ''
}
function drop(event: DragEvent) {
  dragging.value = false
  choose(Array.from(event.dataTransfer?.files || []))
}
</script>
<template>
  <div
    class="kb-upload"
    :class="{ dragging }"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="drop"
  >
    <AppIcon name="upload" :size="24" />
    <div>
      <strong>{{ busy ? '正在上传，请稍候…' : '将资料放进你的知识库' }}</strong>
      <p>拖入文件，或选择上传。文字会在后台提取并建立索引。</p>
      <small
        >TXT / Markdown / 文本 PDF · UTF-8 · 每次 {{ limits.files }} 个 · 单文件 10 MiB · 请求 32
        MiB</small
      >
    </div>
    <button class="kb-primary" :disabled="busy" @click="input?.click()">
      {{ busy ? '上传中…' : '选择文件' }}
    </button>
    <input
      ref="input"
      hidden
      type="file"
      multiple
      :accept="limits.extensions.join(',')"
      @change="onChange"
    />
  </div>
  <p v-if="error" role="alert" class="kb-error">{{ error }}</p>
</template>
