<script setup lang="ts">
import { computed } from 'vue'
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
  highlight: (code, language) => {
    // Syntax highlighting is deferred until the draft stops changing.
    const body =
      !props.streaming && hljs.getLanguage(language)
        ? hljs.highlight(code, { language, ignoreIllegals: true }).value
        : md.utils.escapeHtml(code)
    return `<pre class="code-block"><button type="button" class="code-copy" aria-label="复制代码">复制代码</button><code class="hljs">${body}</code></pre>`
  },
})
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
function handleClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  const citation = target.closest<HTMLElement>('[data-citation]')?.dataset.citation
  if (citation && props.sources?.some((source) => source.citation_id === citation)) {
    emit('citation', citation)
    return
  }
  const button = target.closest('.code-copy')
  if (button) void copy(button.parentElement?.querySelector('code')?.textContent ?? '')
  const link = target.closest('a')
  if (link) {
    link.target = '_blank'
    link.rel = 'noopener noreferrer'
  }
}
</script>
<template>
  <div class="markdown" @click="handleClick" v-html="html"></div>
  <span v-if="feedback" class="copy-feedback" role="status">{{ feedback }}</span>
</template>
