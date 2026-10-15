<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
  type RenderTask,
} from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import AppIcon from '../AppIcon.vue'

GlobalWorkerOptions.workerSrc = workerUrl
const props = defineProps<{ url: string; initialPage?: number; title: string }>()
const canvas = ref<HTMLCanvasElement>()
const container = ref<HTMLElement>()
const page = ref(Math.max(1, props.initialPage || 1))
const total = ref(0)
const zoom = ref(1)
const loading = ref(true)
const error = ref('')
const rendering = ref(false)
let document: PDFDocumentProxy | undefined
let loadTask: ReturnType<typeof getDocument> | undefined
let renderTask: RenderTask | undefined
let version = 0
let disposed = false
let timer: ReturnType<typeof setTimeout> | undefined
let observer: ResizeObserver | undefined

async function render() {
  const ticket = ++version
  renderTask?.cancel()
  if (!document || !canvas.value || !container.value) return
  rendering.value = true
  error.value = ''
  try {
    const pdfPage = await document.getPage(Math.max(1, Math.min(total.value, page.value || 1)))
    if (ticket !== version || disposed) return
    const natural = pdfPage.getViewport({ scale: 1 })
    const width = Math.max(240, container.value.clientWidth - 24) * zoom.value
    const viewport = pdfPage.getViewport({ scale: width / natural.width })
    const ratio = Math.min(window.devicePixelRatio || 1, 2)
    canvas.value.width = Math.floor(viewport.width * ratio)
    canvas.value.height = Math.floor(viewport.height * ratio)
    canvas.value.style.width = `${viewport.width}px`
    canvas.value.style.height = `${viewport.height}px`
    renderTask = pdfPage.render({
      canvas: canvas.value,
      viewport,
      transform: [ratio, 0, 0, ratio, 0, 0],
    })
    await renderTask.promise
  } catch (cause) {
    if (ticket === version && !disposed)
      error.value = cause instanceof Error ? cause.message : '页面渲染失败'
  } finally {
    if (ticket === version && !disposed) rendering.value = false
  }
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    loadTask = getDocument({
      url: props.url,
      cMapUrl: '/pdfjs/cmaps/',
      cMapPacked: true,
      standardFontDataUrl: '/pdfjs/standard_fonts/',
      wasmUrl: '/pdfjs/wasm/',
    })
    document = await loadTask.promise
    if (disposed) return
    total.value = document.numPages
    page.value = Math.min(page.value, total.value)
    await render()
  } catch (cause) {
    if (!disposed)
      error.value = `无法读取 PDF：${cause instanceof Error ? cause.message : '加载失败'}。可重试或打开原始文档。`
  } finally {
    if (!disposed) loading.value = false
  }
}
function changePage(event: Event) {
  const input = event.target as HTMLInputElement
  page.value = Math.max(1, Math.min(total.value, Math.floor(Number(input.value)) || 1))
  input.value = String(page.value)
}
watch([page, zoom], () => {
  if (!loading.value) void render()
})
onMounted(() => {
  void load()
  observer = new ResizeObserver(() => {
    clearTimeout(timer)
    timer = setTimeout(() => void render(), 120)
  })
  if (container.value) observer.observe(container.value)
})
onBeforeUnmount(() => {
  disposed = true
  version++
  observer?.disconnect()
  clearTimeout(timer)
  renderTask?.cancel()
  void loadTask?.destroy()
})
</script>
<template>
  <section class="pdf-reader" aria-label="PDF 原文阅读">
    <div class="pdf-toolbar">
      <button
        class="icon-button"
        aria-label="上一页"
        :disabled="loading || page <= 1"
        @click="page--"
      >
        <AppIcon name="right" class="rotate-back" :size="16" />
      </button>
      <label
        >页码
        <input
          :value="page"
          type="number"
          min="1"
          :max="total || 1"
          :disabled="loading"
          @change="changePage" /></label
      ><span>/ {{ total || '—' }}</span>
      <button
        class="icon-button"
        aria-label="下一页"
        :disabled="loading || page >= total"
        @click="page++"
      >
        <AppIcon name="right" :size="16" />
      </button>
      <label class="pdf-zoom"
        >缩放
        <select v-model="zoom" :disabled="loading">
          <option :value="1">适合宽度</option>
          <option :value="1.5">150%</option>
          <option :value="2">200%</option>
        </select></label
      >
      <button
        v-if="initialPage"
        class="text-action"
        :disabled="loading"
        @click="page = Math.min(initialPage, total)"
      >
        引用页
      </button>
    </div>
    <p v-if="error" class="inline-error" role="alert">
      {{ error }} <button class="text-action" @click="document ? render() : load()">重试</button>
    </p>
    <p v-else class="pdf-status" role="status">
      {{ loading ? '正在读取原文…' : rendering ? '正在绘制页面…' : `正在阅读第 ${page} 页` }}
    </p>
    <div
      ref="container"
      class="pdf-canvas-container"
      tabindex="0"
      aria-label="PDF 页面，可横向滚动查看放大内容"
      :aria-busy="loading || rendering"
    >
      <canvas
        ref="canvas"
        role="img"
        :aria-label="`${title}，第 ${page} 页。文字证据可在上方阅读。`"
      />
    </div>
  </section>
</template>
