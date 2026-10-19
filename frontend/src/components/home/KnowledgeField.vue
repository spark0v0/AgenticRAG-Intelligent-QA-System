<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { createKnowledgeField, type KnowledgeFieldRenderer } from './knowledgeField'

const canvas = ref<HTMLCanvasElement>()
const paused = ref(false)
const expanded = ref(false)
const rendererState = ref<'loading' | 'webgl' | 'fallback'>('loading')
let renderer: KnowledgeFieldRenderer | null = null
let motionPreference: MediaQueryList | undefined
const followMotionPreference = () => {
  paused.value = motionPreference?.matches ?? false
}

function pointAt(event: PointerEvent) {
  if (event.pointerType !== 'mouse' || paused.value) return
  const bounds = canvas.value?.getBoundingClientRect()
  if (!bounds) return
  renderer?.pointAt(
    ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
    ((event.clientY - bounds.top) / bounds.height) * 2 - 1,
  )
}

function resetPointer() {
  renderer?.pointAt(0, 0)
}

onMounted(() => {
  motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
  followMotionPreference()
  motionPreference.addEventListener('change', followMotionPreference)
  if (canvas.value)
    renderer = createKnowledgeField(canvas.value, paused.value, () => {
      rendererState.value = 'fallback'
    })
  rendererState.value = renderer ? 'webgl' : 'fallback'
})
watch(paused, (value) => renderer?.setPaused(value))
watch(expanded, (value) => renderer?.setExpanded(value))
onBeforeUnmount(() => {
  motionPreference?.removeEventListener('change', followMotionPreference)
  renderer?.dispose()
})

// A local, static illustration is also available when WebGL cannot be created.
const fallbackPaths = Array.from({ length: 40 }, (_, index) => {
  const group = Math.floor(index / 8)
  const offset = (index % 8) * 3
  return `M -20 ${500 + group * 22 + offset} C 240 ${650 - group * 34 + offset} 410 ${180 + group * 28 + offset} 830 ${40 + group * 20 + offset}`
})
</script>

<template>
  <div class="knowledge-field" :data-renderer="rendererState">
    <div class="knowledge-field-art" @pointermove="pointAt" @pointerleave="resetPointer">
      <canvas
        ref="canvas"
        aria-hidden="true"
        :class="{ 'is-unavailable': rendererState === 'fallback' }"
      />
      <svg
        v-if="rendererState !== 'webgl'"
        class="knowledge-field-fallback"
        viewBox="0 0 800 650"
        fill="none"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="home-flow-spectrum" x1="0%" y1="100%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#39bcff" />
            <stop offset="55%" stop-color="#5975ff" />
            <stop offset="100%" stop-color="#a38afa" />
          </linearGradient>
        </defs>
        <path
          v-for="(path, index) in fallbackPaths"
          :key="path"
          :d="path"
          stroke="url(#home-flow-spectrum)"
          :opacity="0.14 + (index % 5) * 0.08"
        />
      </svg>
    </div>
    <div
      v-if="rendererState === 'webgl'"
      class="knowledge-field-controls"
      aria-label="视觉效果控制"
    >
      <button
        type="button"
        class="knowledge-field-control"
        :aria-label="expanded ? '聚合光流' : '展开光流'"
        :title="expanded ? '聚合光流' : '展开光流'"
        :aria-pressed="expanded"
        @click="expanded = !expanded"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 18 18"
          fill="none"
          stroke="currentColor"
          stroke-width="1.4"
          aria-hidden="true"
        >
          <path
            v-if="expanded"
            d="M2 6h4V2m10 4h-4V2M2 12h4v4m10-4h-4v4M2 2l4 4m10-4-4 4M2 16l4-4m10 4-4-4"
          />
          <path v-else d="M6 2H2v4m10-4h4v4M2 12v4h4m10-4v4h-4M7 7 2 2m9 5 5-5M7 11l-5 5m9-5 5 5" />
        </svg>
      </button>
      <button
        type="button"
        class="knowledge-field-control"
        :aria-label="paused ? '继续动效' : '暂停动效'"
        :title="paused ? '继续动效' : '暂停动效'"
        @click="paused = !paused"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path v-if="paused" d="m5 3 7 5-7 5Z" fill="currentColor" />
          <path v-else d="M5 3v10M11 3v10" stroke="currentColor" stroke-width="2" />
        </svg>
      </button>
    </div>
  </div>
</template>
