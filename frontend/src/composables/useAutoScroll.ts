import { nextTick, ref, watch, type Ref } from 'vue'

export function useAutoScroll(
  container: Ref<HTMLElement | null>,
  contentKey: () => string,
  enabled: () => boolean = () => true,
) {
  const following = ref(true)
  const onScroll = () => {
    if (!enabled()) return
    const el = container.value
    if (el) following.value = el.scrollHeight - el.scrollTop - el.clientHeight < 100
  }
  async function toBottom() {
    following.value = true
    await nextTick()
    const el = container.value
    if (el && enabled()) el.scrollTop = el.scrollHeight
  }
  watch(contentKey, async () => {
    if (enabled() && following.value) await toBottom()
  })
  return { following, onScroll, toBottom }
}
