<script setup lang="ts">
import type { StageEvent } from '../../types'
import {
  durationLabel,
  nodeLabels,
  runLabels,
  timestampLabel,
} from '../../composables/useRunAnalysis'
defineProps<{
  stages: StageEvent[]
  selected?: string
  span?: number
  bar: (event: StageEvent) => { left: string; width: string }
}>()
defineEmits<{ select: [id: string] }>()
function description(event: StageEvent) {
  return `${nodeLabels[event.data.node] || event.data.node} · 第 ${event.data.round} 轮 · ${runLabels[event.data.status] || event.data.status}\n开始 ${timestampLabel(event.data.started_at)}\n结束 ${timestampLabel(event.data.finished_at)}\n耗时 ${durationLabel(event.data.duration_ms)}`
}
</script>
<template>
  <div class="waterfall-heading">
    <span>节点 / 轮次</span
    ><span
      >0<span>{{ durationLabel(span) }}</span></span
    ><span>耗时</span>
  </div>
  <div class="waterfall" aria-label="执行节点">
    <button
      v-for="event in stages"
      :key="event.data.stage_id"
      class="waterfall-row"
      :class="{ selected: selected === event.data.stage_id }"
      :aria-pressed="selected === event.data.stage_id"
      :title="description(event)"
      @click="$emit('select', event.data.stage_id)"
    >
      <span class="waterfall-node"
        ><i class="status-indicator" :class="event.data.status"></i
        ><span
          >{{ nodeLabels[event.data.node] || event.data.node
          }}<small>{{ event.data.node }} · {{ event.data.round }}</small></span
        ></span
      >
      <span class="waterfall-track"
        ><i
          v-if="span != null && event.data.started_at != null && event.data.duration_ms != null"
          :class="event.data.node"
          :style="bar(event)"
        ></i
        ><span v-else class="muted">{{
          event.data.status === 'running' ? '执行中' : '未记录耗时'
        }}</span></span
      >
      <span class="waterfall-time">{{ durationLabel(event.data.duration_ms) }}</span>
    </button>
  </div>
  <p v-if="!stages.length" class="empty-hint">该记录尚无节点数据。</p>
</template>
