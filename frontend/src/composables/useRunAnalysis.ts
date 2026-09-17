import { computed, type Ref } from 'vue'
import type { RunDetail, Source, StageEvent, ToolEvent } from '../types'

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
  const sources = computed<Source[]>(
    () =>
      run.value?.result?.source_map ??
      run.value?.events.findLast((e) => e.type === 'sources')?.data.items ??
      run.value?.result?.sources?.map((source, index) => ({
        source,
        citation_id: `来源 ${index + 1}`,
      })) ??
      [],
  )
  const duration = computed(() =>
    run.value?.finished_at ? (run.value.finished_at - run.value.started_at) * 1000 : undefined,
  )
  const span = computed(() => {
    if (duration.value != null) return duration.value
    if (run.value?.started_at == null) return undefined
    const ends = stages.value
      .map((e) => e.data.finished_at)
      .filter((end): end is number => end != null)
    return ends.length ? Math.max(0, (Math.max(...ends) - run.value.started_at) * 1000) : undefined
  })
  function bar(event: StageEvent) {
    const left = Math.min(
      99,
      Math.max(
        0,
        (((event.data.started_at - (run.value?.started_at ?? 0)) * 1000) /
          Math.max(1, span.value ?? 0)) *
          100,
      ),
    )
    return {
      left: `${left}%`,
      width: `${Math.min(100 - left, Math.max(0.6, ((event.data.duration_ms ?? 0) / Math.max(1, span.value ?? 0)) * 100))}%`,
    }
  }
  return { stages, tools, sources, duration, span, bar }
}
export function durationLabel(value?: number) {
  return value == null
    ? '未记录'
    : value < 1000
      ? `${value.toFixed(0)} ms`
      : `${(value / 1000).toFixed(2)} s`
}
export function timestampLabel(value?: number) {
  if (value == null) return '未记录'
  return (
    new Date(value * 1000).toLocaleString('zh-CN', { hour12: false }) +
    `.${String(Math.floor((value % 1) * 1000)).padStart(3, '0')}`
  )
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
