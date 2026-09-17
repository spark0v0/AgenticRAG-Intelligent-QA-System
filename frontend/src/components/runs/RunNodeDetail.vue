<script setup lang="ts">
import type { StageEvent, ToolEvent } from '../../types'
import {
  durationLabel,
  nodeLabels,
  runLabels,
  timestampLabel,
} from '../../composables/useRunAnalysis'
import AppIcon from '../AppIcon.vue'
defineProps<{ stage: StageEvent; tools: ToolEvent[] }>()
</script>
<template>
  <section class="node-inspector" aria-label="节点详情">
    <header>
      <span class="node-icon"><AppIcon name="branch" :size="19" /></span>
      <div>
        <h3>{{ nodeLabels[stage.data.node] || stage.data.node }}</h3>
        <span
          >第 {{ stage.data.round }} 轮 ·
          {{ runLabels[stage.data.status] || stage.data.status }}</span
        >
      </div>
      <span class="subtle-badge">{{ durationLabel(stage.data.duration_ms) }}</span>
    </header>
    <dl class="node-times">
      <div>
        <dt>开始</dt>
        <dd>{{ timestampLabel(stage.data.started_at) }}</dd>
      </div>
      <div>
        <dt>结束</dt>
        <dd>{{ timestampLabel(stage.data.finished_at) }}</dd>
      </div>
    </dl>
    <div class="node-io">
      <div>
        <span class="tiny-label">输入摘要</span>
        <p>{{ stage.data.input || '未记录' }}</p>
      </div>
      <div>
        <span class="tiny-label">{{
          stage.data.status === 'error' ? '失败详情' : '输出摘要'
        }}</span>
        <p :class="{ 'inline-error': stage.data.status === 'error' }">
          {{ stage.data.output || '暂无输出' }}
        </p>
      </div>
    </div>
    <details v-if="stage.data.metadata" class="raw-details">
      <summary>结构化节点数据</summary>
      <pre>{{ JSON.stringify(stage.data.metadata, null, 2) }}</pre>
    </details>
    <div v-if="tools.length" class="node-tools">
      <span class="tiny-label">节点期间的工具调用</span>
      <details v-for="tool in tools" :key="tool.data.call_id" class="tool-call">
        <summary>
          <AppIcon name="tool" :size="15" /><strong>{{ tool.data.tool }}</strong
          ><span>{{ runLabels[tool.data.status] || tool.data.status }}</span>
        </summary>
        <small>{{ tool.data.protocol }} · {{ durationLabel(tool.data.duration_ms) }}</small>
        <p v-if="tool.data.error" class="inline-error">{{ tool.data.error }}</p>
        <pre>{{
          JSON.stringify({ input: tool.data.input, output: tool.data.output }, null, 2)
        }}</pre>
      </details>
    </div>
  </section>
</template>
