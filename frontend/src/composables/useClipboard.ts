import { onUnmounted, ref } from 'vue'

export function useClipboard() {
  const feedback = ref('')
  let timer: ReturnType<typeof setTimeout> | undefined
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      feedback.value = '已复制'
    } catch {
      feedback.value = '复制失败，请手动选择文字'
    }
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => (feedback.value = ''), 2000)
  }
  onUnmounted(() => {
    if (timer) clearTimeout(timer)
  })
  return { feedback, copy }
}
