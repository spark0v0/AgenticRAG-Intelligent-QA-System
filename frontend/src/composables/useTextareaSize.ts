import { onUnmounted, watch, type Ref } from 'vue'

export function useTextareaSize(element: Ref<HTMLTextAreaElement | null>, value: () => string) {
  let observer: ResizeObserver | undefined
  let frame = 0
  function resize() {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => {
      const input = element.value
      if (!input) return
      // CSS supplies the responsive minimum and maximum; extra lines scroll inside.
      input.style.height = 'auto'
      input.style.height = `${input.scrollHeight}px`
    })
  }
  watch(value, resize, { flush: 'post' })
  watch(
    element,
    (input) => {
      observer?.disconnect()
      if (!input) return
      let width = -1
      observer = new ResizeObserver(([entry]) => {
        if (entry && entry.contentRect.width !== width) {
          width = entry.contentRect.width
          resize()
        }
      })
      observer.observe(input)
      resize()
    },
    { flush: 'post' },
  )
  onUnmounted(() => {
    observer?.disconnect()
    cancelAnimationFrame(frame)
  })
}
