import { nextTick, ref, useId } from 'vue'

// Automatic activation for local panels whose content is already available.
export function useTabs(ids: readonly string[]) {
  const tab = ref(ids[0]!)
  const groupId = useId()
  const panelId = `${groupId}-panel`
  const tabId = (id: string) => `${groupId}-${id}`
  async function onTabKeydown(event: KeyboardEvent) {
    const index = ids.indexOf(tab.value)
    const next =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? ids.length - 1
          : event.key === 'ArrowRight'
            ? (index + 1) % ids.length
            : event.key === 'ArrowLeft'
              ? (index + ids.length - 1) % ids.length
              : -1
    if (next < 0 || event.altKey || event.ctrlKey || event.metaKey) return
    event.preventDefault()
    const list = event.currentTarget as HTMLElement
    tab.value = ids[next]!
    await nextTick()
    list.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')?.focus()
  }
  return { tab, panelId, tabId, onTabKeydown }
}
