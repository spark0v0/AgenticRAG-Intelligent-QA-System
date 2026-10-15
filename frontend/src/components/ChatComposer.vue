<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { ElSelect, ElOption } from 'element-plus'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import { useWorkbench } from '../stores/workbench'
import type { ImageAttachment } from '../types'
import AppIcon from './AppIcon.vue'
import { useKnowledge } from '../stores/knowledge'
import { useTextareaSize } from '../composables/useTextareaSize'

const store = useWorkbench()
const knowledge = useKnowledge()
const textarea = ref<HTMLTextAreaElement | null>(null)
useTextareaSize(textarea, () => store.current?.draft ?? '')
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
let fileVersion = 0
function cancelReaders() {
  fileVersion++
  for (const reader of readers) reader.abort()
  readers.clear()
  fileBusy.value = false
}
onUnmounted(cancelReaders)
watch(() => store.currentId, cancelReaders, { flush: 'sync' })
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
  if (!conversation || fileBusy.value || store.busy) return
  const version = ++fileVersion
  const ownedReaders = new Set<FileReader>()
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
            ownedReaders.add(reader)
            reader.onloadend = () => {
              readers.delete(reader)
              ownedReaders.delete(reader)
            }
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
    if (version === fileVersion) conversation.images.push(...images)
  } catch (e) {
    if (version === fileVersion)
      conversation.error = e instanceof Error ? e.message : '图片读取失败'
  } finally {
    for (const reader of ownedReaders) reader.abort()
    if (version === fileVersion) {
      fileBusy.value = false
      input.value = ''
    }
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
    <p v-if="store.current?.restoreNotice" class="notice" role="status">
      {{ store.current.restoreNotice }}
    </p>
    <div v-if="store.current?.error" class="inline-error" role="alert">
      {{ store.current.error }}
    </div>
    <div class="composer-context">
      <fieldset class="search-scope" :disabled="store.busy || store.thinking === 'quick'">
        <legend class="sr-only">检索范围</legend>
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
          <AppIcon v-if="scope.value === 'web'" name="globe" :size="14" /><AppIcon
            v-else-if="scope.value === 'local'"
            name="book"
            :size="14"
          /><AppIcon v-else-if="scope.value === 'auto'" name="spark" :size="14" /><AppIcon
            v-else
            name="layers"
            :size="14"
          /><span>{{ scope.label }}</span>
        </label>
      </fieldset>
      <div v-if="store.thinking !== 'quick' && store.searchScope !== 'web'" class="kb-chat-select">
        <label for="chat-knowledge"><AppIcon name="book" :size="14" />资料</label>
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
        <RouterLink
          to="/knowledge"
          class="manage-knowledge"
          aria-label="管理知识库"
          title="管理知识库"
          ><AppIcon name="settings" :size="16"
        /></RouterLink>
      </div>
      <p v-if="knowledgeError" class="kb-error">{{ knowledgeError }}</p>
    </div>
    <div class="composer" :class="{ 'is-busy': store.busy }">
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
        ref="textarea"
        v-model="store.current.draft"
        aria-label="输入问题"
        placeholder="问点什么，或围绕你的资料展开提问…"
        maxlength="20000"
        rows="2"
        :disabled="store.busy || store.loadingSession"
        @keydown="handleKey"
      ></textarea>
      <div class="composer-toolbar">
        <div class="composer-options">
          <input
            ref="fileInput"
            hidden
            type="file"
            :disabled="
              store.busy || fileBusy || store.loadingSession || !store.profile?.supports_vision
            "
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            aria-label="上传图片"
            @change="attach"
          />
          <button
            class="icon-button"
            :disabled="
              store.busy || fileBusy || store.loadingSession || !store.profile?.supports_vision
            "
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
          title="停止本轮生成"
          :disabled="store.current?.cancelling"
          :aria-label="store.current?.cancelling ? '正在停止生成' : '停止生成'"
          @click="store.cancel()"
        >
          <AppIcon name="stop" :size="16" /><span class="send-label">{{
            store.current?.cancelling ? '停止中…' : '停止'
          }}</span>
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
          <span class="send-label">发送</span><AppIcon name="arrow" :size="17" />
        </button>
      </div>
    </div>
    <div class="composer-footnote">
      <span class="composer-shortcut"
        ><kbd>Enter</kbd> 发送 <span>·</span> <kbd>Shift + Enter</kbd> 换行</span
      >
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
