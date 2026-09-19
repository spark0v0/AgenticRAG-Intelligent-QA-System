<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElSelect, ElOption } from 'element-plus'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import { useWorkbench } from '../stores/workbench'
import type { ImageAttachment } from '../types'
import AppIcon from './AppIcon.vue'
import { useKnowledge } from '../stores/knowledge'

const store = useWorkbench()
const knowledge = useKnowledge()
const knowledgeError = ref('')
const knowledgeController = new AbortController()
onMounted(() => {
  void knowledge.refresh(knowledgeController.signal).catch(() => {
    if (!knowledgeController.signal.aborted) knowledgeError.value = '知识库列表暂时不可用'
  })
})
onUnmounted(() => knowledgeController.abort())
const fileInput = ref<HTMLInputElement | null>(null)
const fileBusy = ref(false)
const readers = new Set<FileReader>()
onUnmounted(() => {
  for (const reader of readers) reader.abort()
  readers.clear()
})
const modes = [
  { value: '', label: '自动决策' },
  { value: 'quick', label: '快速回答' },
  { value: 'retrieval', label: '知识检索' },
  { value: 'deep', label: '深度分析' },
]
async function attach(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  const conversation = store.current
  if (!conversation) return
  fileBusy.value = true
  conversation.error = ''
  try {
    const limit = store.system?.image_limits ?? { count: 4, bytes: 4 * 1024 * 1024 }
    if (conversation.images.length + files.length > limit.count)
      throw new Error(`每条消息最多添加 ${limit.count} 张图片。`)
    const images = await Promise.all(
      files.map(
        (file) =>
          new Promise<ImageAttachment>((resolve, reject) => {
            if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(file.type)) {
              reject(new Error('请选择 PNG、JPEG、WebP 或 GIF 图片。'))
              return
            }
            if (!file.size || file.size > limit.bytes) {
              reject(
                new Error(`${file.name} 不能超过 ${limit.bytes / 1024 / 1024}MB，且不能为空。`),
              )
              return
            }
            const reader = new FileReader()
            readers.add(reader)
            reader.onloadend = () => readers.delete(reader)
            reader.onabort = () => reject(new Error('图片读取已取消'))
            reader.onload = () =>
              resolve({
                type: 'image',
                filename: file.name,
                mime_type: file.type,
                size: file.size,
                data_url: String(reader.result),
              })
            reader.onerror = () => reject(new Error(`无法读取 ${file.name}`))
            reader.readAsDataURL(file)
          }),
      ),
    )
    conversation.images.push(...images)
  } catch (e) {
    conversation.error = e instanceof Error ? e.message : '图片读取失败'
  } finally {
    fileBusy.value = false
    input.value = ''
  }
}
function handleKey(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault()
    if (!fileBusy.value) void store.send()
  }
}
</script>
<template>
  <div class="composer-area">
    <div v-if="store.current?.error" class="inline-error" role="alert">
      {{ store.current.error }}
    </div>
    <div class="composer" :class="{ 'is-busy': store.busy }">
      <fieldset class="search-scope" :disabled="store.busy || store.thinking === 'quick'">
        <legend>检索范围</legend>
        <label
          v-for="scope in [
            { value: 'auto', label: '自动' },
            { value: 'local', label: '本地知识' },
            { value: 'web', label: '联网搜索' },
            { value: 'all', label: '本地 + 联网' },
          ]"
          :key="scope.value"
        >
          <input
            v-model="store.searchScope"
            type="radio"
            name="search-scope"
            :value="scope.value"
            :disabled="!!knowledge.selectedId && scope.value === 'web'"
          />
          <span>{{ scope.label }}</span>
        </label>
      </fieldset>
      <div v-if="store.thinking !== 'quick' && store.searchScope !== 'web'" class="kb-chat-select">
        <label for="chat-knowledge">检索资料</label>
        <ElSelect
          id="chat-knowledge"
          v-model="knowledge.selectedId"
          :empty-values="[null, undefined]"
          :disabled="store.busy"
          aria-label="选择知识库"
          :teleported="false"
        >
          <ElOption value="" label="项目内置资料（旧版检索）" />
          <ElOption
            v-if="
              knowledge.selectedId &&
              !knowledge.libraries.some((item) => item.id === knowledge.selectedId)
            "
            :value="knowledge.selectedId"
            label="所选知识库不可用，请重新选择"
            disabled
          />
          <ElOption
            v-for="item in knowledge.libraries"
            :key="item.id"
            :value="item.id"
            :label="item.name"
          />
        </ElSelect>
        <RouterLink to="/knowledge">管理资料</RouterLink>
      </div>
      <p v-if="knowledgeError" class="kb-error">{{ knowledgeError }}</p>
      <div v-if="store.current?.images.length" class="attachment-list">
        <div v-for="(image, index) in store.current.images" :key="index" class="attachment">
          <img :src="image.data_url" :alt="image.filename" /><span>{{ image.filename }}</span
          ><button
            :disabled="store.busy"
            :aria-label="`移除 ${image.filename}`"
            @click="store.current.images.splice(index, 1)"
          >
            <AppIcon name="close" :size="13" />
          </button>
        </div>
      </div>
      <textarea
        v-if="store.current"
        v-model="store.current.draft"
        aria-label="输入问题"
        placeholder="输入问题，或继续追问…"
        maxlength="20000"
        rows="2"
        :disabled="store.busy || store.loadingSession"
        @keydown="handleKey"
      ></textarea>
      <div class="composer-toolbar">
        <div class="composer-options">
          <input
            ref="fileInput"
            class="sr-only"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            aria-label="上传图片"
            @change="attach"
          />
          <button
            class="icon-button"
            :disabled="store.busy || fileBusy || !store.profile?.supports_vision"
            :title="
              store.profile?.supports_vision ? '添加图片（每张最多 4MB）' : '所选模型不支持图片'
            "
            aria-label="添加图片"
            @click="fileInput?.click()"
          >
            <AppIcon name="attach" :size="18" />
          </button>
          <span class="toolbar-divider"></span>
          <ElSelect
            v-model="store.thinking"
            :empty-values="[null, undefined]"
            class="mode-select"
            aria-label="思考模式"
            :disabled="store.busy"
            :teleported="false"
            ><ElOption
              v-for="item in modes"
              :key="item.value"
              :label="item.label"
              :value="item.value"
              :disabled="!!knowledge.selectedId && item.value === 'quick'"
          /></ElSelect>
          <ElSelect
            v-model="store.model"
            class="model-select"
            aria-label="选择模型"
            :disabled="store.busy || !store.system"
            :teleported="false"
            ><ElOption
              v-for="item in store.system?.model_profiles"
              :key="item.id"
              :label="item.label"
              :value="item.id"
              :disabled="!item.configured"
          /></ElSelect>
        </div>
        <button
          v-if="store.busy"
          class="send-button stop-button"
          aria-label="停止生成"
          title="停止本轮生成"
          @click="store.cancel()"
        >
          <AppIcon name="stop" :size="16" />
        </button>
        <button
          v-else
          class="send-button"
          aria-label="发送问题"
          :disabled="
            (!store.current?.draft.trim() && !store.current?.images.length) ||
            !store.system ||
            !store.profile?.configured ||
            store.loading ||
            store.loadingSession ||
            fileBusy
          "
          @click="store.send()"
        >
          <AppIcon name="arrow" :size="19" />
        </button>
      </div>
    </div>
    <div class="composer-footnote">
      <span>{{
        !store.profile?.configured
          ? '所选模型尚未配置'
          : store.hasPending && !store.busy
            ? '其他会话正在后台运行'
            : 'AI 回答可能存在偏差，请结合来源核实重要信息'
      }}</span>
      <RouterLink v-if="!store.profile?.configured" to="/providers"
        >配置供应商 <AppIcon name="right" :size="12"
      /></RouterLink>
    </div>
  </div>
</template>
