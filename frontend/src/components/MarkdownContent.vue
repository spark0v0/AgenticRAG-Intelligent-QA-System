<script setup lang="ts">
import { computed, onUnmounted } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import css from 'highlight.js/lib/languages/css'
import 'highlight.js/styles/github.css'
import { useClipboard } from '../composables/useClipboard'
import type { Source } from '../types'

const props = defineProps<{ content: string; streaming?: boolean; sources?: Source[] }>()
const emit = defineEmits<{ citation: [id: string] }>()
const { copy, feedback } = useClipboard()
for (const [name, language] of Object.entries({ javascript, typescript, python, json, css }))
  hljs.registerLanguage(name, language)
const md: MarkdownIt = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})
md.renderer.rules.fence = (tokens, index) => {
  const token = tokens[index]!
  const language = token.info.trim().split(/\s+/)[0] || ''
  const label = md.utils.escapeHtml(language || '纯文本')
  // Keep the toolbar outside the horizontal scroller; defer highlighting while streaming.
  const body =
    !props.streaming && hljs.getLanguage(language)
      ? hljs.highlight(token.content, { language, ignoreIllegals: true }).value
      : md.utils.escapeHtml(token.content)
  return `<div class="code-block"><div class="code-header"><span>${label}</span><button type="button" class="code-copy" aria-label="复制代码">复制代码</button></div><pre tabindex="0" aria-label="${label}代码"><code class="hljs">${body}</code></pre></div>`
}
const renderLink = md.renderer.rules.link_open
md.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
  tokens[index]!.attrSet('target', '_blank')
  tokens[index]!.attrSet('rel', 'noopener noreferrer')
  return renderLink
    ? renderLink(tokens, index, options, env, renderer)
    : renderer.renderToken(tokens, index, options)
}
// Only explicit backend source IDs become citations. Inline/fenced code remains untouched.
md.inline.ruler.after('link', 'source_reference', (state, silent) => {
  if (silent) return false
  if ('linkLevel' in state && typeof state.linkLevel === 'number' && state.linkLevel > 0)
    return false
  const match = /^\[(S\d+)\]/.exec(state.src.slice(state.pos))
  if (!match || !props.sources?.some((source) => source.citation_id === match[1])) return false
  const token = state.push('source_reference', '', 0)
  token.content = match[1]!
  state.pos += match[0].length
  return true
})
md.renderer.rules.source_reference = (tokens, index) => {
  const id = md.utils.escapeHtml(tokens[index]!.content)
  return `<button type="button" class="citation-link" data-citation="${id}" aria-label="查看来源 ${id}">[${id}]</button>`
}
const html = computed(() =>
  DOMPurify.sanitize(md.render(props.content), {
    FORBID_TAGS: ['img', 'style', 'iframe', 'form'],
    ADD_ATTR: ['target', 'rel'],
  }),
)
const copyTimers = new Map<HTMLButtonElement, ReturnType<typeof setTimeout>>()
onUnmounted(() => {
  copyTimers.forEach(clearTimeout)
  copyTimers.clear()
})
async function handleClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  const citation = target.closest<HTMLElement>('[data-citation]')?.dataset.citation
  if (citation && props.sources?.some((source) => source.citation_id === citation)) {
    emit('citation', citation)
    return
  }
  const button = target.closest<HTMLButtonElement>('.code-copy')
  if (!button) return
  const code = button.closest('.code-block')?.querySelector('code')?.textContent
  if (code == null) return
  const copied = await copy(code)
  if (copied === undefined || !button.isConnected) return
  // v-html owns the markup. Update only the clicked control, without re-rendering code.
  clearTimeout(copyTimers.get(button))
  button.textContent = copied ? '已复制' : '复制失败，请手动选择'
  copyTimers.set(
    button,
    setTimeout(() => {
      if (button.isConnected) button.textContent = '复制代码'
      copyTimers.delete(button)
    }, 2000),
  )
}
</script>
<template>
  <div class="markdown" @click="handleClick" v-html="html"></div>
  <span v-if="feedback" class="sr-only" role="status">{{ feedback }}</span>
</template>
