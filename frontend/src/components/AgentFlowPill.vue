<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '../types'
import AppIcon from './AppIcon.vue'

const props = defineProps<{ message: Message }>()
defineEmits<{ inspect: [runId: string] }>()

const routeLabels: Record<string, string> = {
  planning: '规划分析',
  retrieval: '检索增强',
  direct: '直接回答',
}

const scopeLabels: Record<string, string> = {
  auto: '自动检索',
  local: '本地 RAG',
  web: '联网搜索',
  all: '混合检索',
}

const currentStage = computed(() => {
  const phase = props.message.phase || ''
  if (phase.includes('识别') || phase.includes('路由')) return { name: 'Router', label: '意图路由' }
  if (phase.includes('规划')) return { name: 'Planner', label: '任务规划' }
  if (phase.includes('检索')) return { name: 'Retriever', label: '多路检索' }
  if (phase.includes('模型') || phase.includes('回答') || props.message.status === 'streaming')
    return { name: 'Generator', label: '答案生成' }
  if (phase.includes('检查') || phase.includes('引用') || phase.includes('评审'))
    return { name: 'Critic', label: '质量评审' }
  return { name: 'Agent', label: '智能分析' }
})

const queryVariantsCount = computed(
  () => props.message.result?.retrieval_plan?.query_variants?.length ?? 0,
)

const completedRoute = computed(() => {
  const r = props.message.result?.routing?.route
  if (r === 'planning' && queryVariantsCount.value > 1) {
    return `规划拆解 (${queryVariantsCount.value}个子查询)`
  }
  return (r && routeLabels[r]) || '意图已识别'
})

const retrievalScopeText = computed(() => {
  const scope = props.message.result?.retrieval_plan?.search_scope
  return (scope && scopeLabels[scope]) || '检索回答'
})

const sourceCount = computed(() => props.message.result?.source_map?.length ?? 0)

const criticEvaluation = computed(() => {
  const evaluation = props.message.result?.evaluation
  if (!evaluation) return { text: '校验完成', hasIssues: false }
  if (evaluation.unresolved || evaluation.issues?.length) {
    return {
      text: `${evaluation.issues.length}项待核实`,
      hasIssues: true,
    }
  }
  if (evaluation.revision_count && evaluation.revision_count > 0) {
    return {
      text: `自纠错${evaluation.revision_count}轮通过`,
      hasIssues: false,
    }
  }
  return { text: '校验通过', hasIssues: false }
})

const timingLabel = computed(() => {
  const timing = props.message.result?.timing
  if (!timing) return undefined
  if (timing.total_ms > 0) return `${(timing.total_ms / 1000).toFixed(1)}s`
  if (timing.first_delta_ms != null) return `${(timing.first_delta_ms / 1000).toFixed(1)}s`
  return undefined
})

const isRunning = computed(
  () => props.message.status === 'submitting' || props.message.status === 'streaming',
)
const isSuccess = computed(() => props.message.status === 'success')
</script>

<template>
  <div
    v-if="isRunning || isSuccess"
    class="agent-flow-pill-container"
    :class="{ 'is-running': isRunning, 'is-success': isSuccess }"
  >
    <!-- Running State: Animated pulsing pill with active agent -->
    <button
      v-if="isRunning"
      type="button"
      class="agent-flow-pill running-pill thinking-indicator"
      :title="message.run_id ? '点击查看实时执行进度' : undefined"
      :disabled="!message.run_id"
      @click="message.run_id && $emit('inspect', message.run_id)"
    >
      <span class="pill-pulse-dot"></span>
      <span class="pill-agent-badge">{{ currentStage.name }}</span>
      <span class="pill-divider">·</span>
      <span class="pill-phase-text">{{
        message.phase || (message.status === 'streaming' ? '正在流式生成回答…' : '正在分析执行…')
      }}</span>
      <AppIcon v-if="message.run_id" name="right" :size="12" class="pill-arrow-icon" />
    </button>

    <!-- Completed State: Interactive multi-agent orchestration badge -->
    <button
      v-else-if="isSuccess && message.run_id"
      type="button"
      class="agent-flow-pill success-pill answer-evidence-summary"
      title="点击查看智能体完整执行详情"
      @click="$emit('inspect', message.run_id)"
    >
      <div class="pill-node node-router">
        <AppIcon name="spark" :size="13" />
        <span>Router {{ completedRoute }}</span>
      </div>

      <span class="pill-separator">→</span>

      <div class="pill-node node-retriever">
        <AppIcon name="book" :size="13" />
        <span>Retriever {{ retrievalScopeText }} · {{ sourceCount }}篇来源</span>
      </div>

      <span class="pill-separator">→</span>

      <div class="pill-node node-critic" :class="{ 'has-warning': criticEvaluation.hasIssues }">
        <AppIcon :name="criticEvaluation.hasIssues ? 'alert' : 'shield'" :size="13" />
        <span>Critic {{ criticEvaluation.text }}</span>
      </div>

      <span v-if="timingLabel" class="pill-timing-tag">
        <AppIcon name="clock" :size="11" />
        {{ timingLabel }}
      </span>

      <AppIcon name="diagonal" :size="12" class="pill-ext-icon" />
    </button>
  </div>
</template>

<style scoped lang="scss">
.agent-flow-pill-container {
  display: flex;
  align-items: center;
  margin-bottom: 14px;
}

.agent-flow-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border-radius: var(--radius-md);
  font-size: 13px;
  background: var(--surface);
  border: 1px solid var(--line);
  color: var(--text);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);

  &:hover {
    border-color: var(--accent);
    box-shadow: 0 0 16px -2px rgba(0, 210, 255, 0.25);
    transform: translateY(-1px);
  }

  &:active {
    transform: translateY(0);
  }

  &:disabled {
    cursor: default;
    transform: none;
    box-shadow: none;
  }
}

.running-pill {
  background: linear-gradient(90deg, rgba(0, 210, 255, 0.08) 0%, rgba(56, 189, 248, 0.03) 100%);
  border-color: rgba(0, 210, 255, 0.3);

  .pill-pulse-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 10px var(--accent);
    animation: pill-pulse 1.6s infinite ease-in-out;
  }

  .pill-agent-badge {
    font-weight: 600;
    color: var(--accent);
    font-family: 'Inter', ui-monospace, monospace;
    font-size: 12px;
    letter-spacing: 0.2px;
  }

  .pill-divider {
    color: var(--muted);
    opacity: 0.6;
  }

  .pill-phase-text {
    color: var(--text);
    font-size: 13px;
  }

  .pill-arrow-icon {
    color: var(--muted);
    margin-left: 2px;
    opacity: 0.7;
  }
}

.success-pill {
  background: linear-gradient(90deg, rgba(15, 23, 42, 0.6) 0%, rgba(21, 30, 54, 0.8) 100%);
  border-color: rgba(0, 210, 255, 0.18);
  backdrop-filter: blur(8px);
  flex-wrap: wrap;

  .pill-node {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12.5px;
    font-weight: 500;
    color: var(--muted);
    transition: color 0.15s ease;

    &.node-router {
      color: var(--text);
    }
    &.node-retriever {
      color: var(--accent);
    }
    &.node-critic {
      color: #38bdf8;
      &.has-warning {
        color: var(--warning);
      }
    }
  }

  .pill-separator {
    color: var(--muted);
    opacity: 0.4;
    font-size: 11px;
    user-select: none;
  }

  .pill-timing-tag {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 1px 6px;
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.05);
    font-size: 11px;
    font-family: 'Inter', monospace;
    color: var(--muted);
    margin-left: 4px;
  }

  .pill-ext-icon {
    color: var(--muted);
    opacity: 0.6;
    margin-left: 2px;
    transition:
      opacity 0.15s ease,
      transform 0.15s ease;
  }

  &:hover .pill-ext-icon {
    opacity: 1;
    transform: translate(1px, -1px);
    color: var(--accent);
  }
}

@keyframes pill-pulse {
  0% {
    transform: scale(0.9);
    opacity: 0.6;
  }
  50% {
    transform: scale(1.25);
    opacity: 1;
  }
  100% {
    transform: scale(0.9);
    opacity: 0.6;
  }
}
</style>
