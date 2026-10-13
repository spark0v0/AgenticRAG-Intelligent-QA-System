import { onUnmounted, ref } from 'vue'

export function useClipboard() {
  const feedback = ref('')
  let timer: ReturnType<typeof setTimeout> | undefined
  let version = 0
  let disposed = false
  async function copy(text: string) {
    const request = ++version
    let copied = false
    try {
      await navigator.clipboard.writeText(text)
      copied = true
    } catch {
      // Keep the source text selectable when clipboard access is denied.
    }
    if (disposed || request !== version) return undefined
    feedback.value = copied ? '已复制' : '复制失败，请手动选择文字'
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => (feedback.value = ''), 2000)
    return copied
  }
  onUnmounted(() => {
    disposed = true
    version++
    if (timer) clearTimeout(timer)
  })
  return { feedback, copy }
}
