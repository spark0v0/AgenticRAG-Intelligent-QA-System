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

const props = defineProps<{ content: string; streaming?: boolean }>()
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
const html = computed(() =>
  DOMPurify.sanitize(md.render(props.content), {
    FORBID_TAGS: ['img', 'style', 'iframe', 'form'],
    ADD_ATTR: ['target', 'rel'],
  }),
)
function handleClick(event: MouseEvent) {
  const target = event.target as HTMLElement
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
