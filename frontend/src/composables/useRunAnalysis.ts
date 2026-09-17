import { computed, type Ref } from 'vue'
import type { RunDetail, StageEvent, ToolEvent } from '../types'

export const nodeLabels: Record<string, string> = {
  router: '意图路由',
  planner: '任务规划',
  retriever: '信息检索',
  generator: '答案生成',
  critic: '质量评审',
}
export const runLabels: Record<string, string> = {
  running: '执行中',
  success: '已完成',
  error: '失败',
  cancelled: '已取消',
  timeout: '超时',
}
export function useRunAnalysis(run: Ref<RunDetail | undefined>) {
  const stages = computed(() => {
    const latest = new Map<string, StageEvent>()
    run.value?.events.forEach((e) => {
      if (e.type === 'stage') latest.set(e.data.stage_id, e)
    })
    return [...latest.values()]
  })
  const tools = computed(() => {
    const latest = new Map<string, ToolEvent>()
    run.value?.events.forEach((e) => {
      if (e.type === 'tool') latest.set(e.data.call_id, e)
    })
    return [...latest.values()]
  })
  const sources = computed(
    () =>
      run.value?.result?.source_map ??
      run.value?.events.findLast((e) => e.type === 'sources')?.data.items ??
      [],
  )
  const duration = computed(() =>
    run.value?.finished_at ? (run.value.finished_at - run.value.started_at) * 1000 : undefined,
  )
  const span = computed(() =>
    Math.max(
      1,
      duration.value ??
        Math.max(
          0,
          ...stages.value.map(
            (e) =>
              ((e.data.finished_at ?? e.data.started_at) - (run.value?.started_at ?? 0)) * 1000,
          ),
        ),
    ),
  )
  function bar(event: StageEvent) {
    const left = Math.min(
      99,
      Math.max(
        0,
        (((event.data.started_at - (run.value?.started_at ?? 0)) * 1000) / span.value) * 100,
      ),
    )
    return {
      left: `${left}%`,
      width: `${Math.min(100 - left, Math.max(0.6, ((event.data.duration_ms ?? 0) / span.value) * 100))}%`,
    }
  }
  return { stages, tools, sources, duration, span, bar }
}
export function durationLabel(value?: number) {
  return value == null
    ? '进行中'
    : value < 1000
      ? `${value.toFixed(0)} ms`
      : `${(value / 1000).toFixed(2)} s`
}
export function sourceLabel(value: string) {
  return /^[a-z]:[\\/]/i.test(value) ? value.split(/[\\/]/).at(-1) || value : value
}
export function safeSourceUrl(value: string) {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined
  } catch {
    return undefined
  }
}
