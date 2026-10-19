import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useAppearance = defineStore('appearance', () => {
  const theme = ref<'light' | 'dark'>('dark')
  try {
    if (localStorage.getItem('rag-theme') === 'light') theme.value = 'light'
  } catch {
    /* Theme storage is optional. */
  }
  function toggleTheme() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
    try {
      localStorage.setItem('rag-theme', theme.value)
    } catch {
      /* Storage is optional. */
    }
  }
  return { theme, toggleTheme }
})
