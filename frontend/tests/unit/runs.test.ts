import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import * as client from '../../src/api/client'
import { useWorkbench } from '../../src/stores/workbench'
import RunsView from '../../src/views/RunsView.vue'
vi.mock('../../src/components/knowledge/EvidenceButton.vue', () => ({ default: { template: '<span />' } }))

beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()); vi.stubGlobal('matchMedia', () => ({ matches: false })) })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
const detail = (id: string, status = 'success') => ({ id, session_id: `session-${id}`, query: id, status, started_at: 1, events: [] })
async function mounted() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/runs', component: RunsView }, { path: '/chat', component: { template: '<div />' } }] })
  await router.push('/runs?run=A')
  const wrapper = mount(RunsView, { global: { plugins: [router], stubs: { RunWaterfall: true, RunNodeDetail: true, MarkdownContent: true } } })
  await flushPromises()
  return { router, wrapper }
}
it('invalidates return-to-chat when the selected run changes during loading', async () => {
  vi.spyOn(client, 'requestJson').mockImplementation(async path => path.startsWith('/runs?') ? { items: [detail('A'), detail('B')], total: 2 } : detail(path.split('/').at(-1)!))
  const store = useWorkbench()
  let release!: (value: boolean) => void
  const load = vi.spyOn(store, 'loadSession').mockImplementation(() => new Promise(resolve => { release = resolve }))
  const { router, wrapper } = await mounted()
  await wrapper.findAll('button').find(button => button.text().includes('回到会话'))!.trigger('click')
  expect(load.mock.calls[0]?.[0]).toBe('session-A')
  await router.replace('/runs?run=B')
  await flushPromises()
  expect(load.mock.calls[0]?.[1]?.aborted).toBe(true)
  release(true)
  await flushPromises()
  expect(store.selectedRun).toBe('')
  expect(router.currentRoute.value.path).toBe('/runs')
  wrapper.unmount()
})
it('recovers read-only polling after a transient failure without resubmitting a question', async () => {
  vi.useFakeTimers()
  let reads = 0
  vi.spyOn(client, 'requestJson').mockImplementation(async path => {
    if (path.startsWith('/runs?')) return { items: [detail('A', 'running')], total: 1 }
    reads++
    if (reads === 2) throw new Error('temporary network interruption')
    return detail('A', reads === 1 ? 'running' : 'success')
  })
  const { wrapper } = await mounted()
  await vi.advanceTimersByTimeAsync(2000)
  await flushPromises()
  expect(wrapper.text()).toContain('temporary network interruption')
  await vi.advanceTimersByTimeAsync(2000)
  await flushPromises()
  expect(reads).toBe(3)
  expect(wrapper.find('.status-badge').text()).toBe('已完成')
  expect(wrapper.text()).not.toContain('temporary network interruption')
  wrapper.unmount()
})
