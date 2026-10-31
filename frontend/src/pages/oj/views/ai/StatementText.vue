<template>
  <span :key="source" v-katex class="studio-statement-text"><template v-for="(part, index) in parts" :key="index"><code v-if="part.code">{{ part.text }}</code><template v-else>{{ part.text }}</template></template></span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ text: { type: String, default: '' } })
const source = computed(() => typeof props.text === 'string' ? props.text : '')
// Keep the statement as text. `$...$` segments stay single text nodes for KaTeX auto-render
// (keyed so Vue never patches nodes KaTeX replaced); code notation is emphasized elsewhere
// without interpreting HTML or changing the source used for notebook exports and evaluation.
const math = /\$\$[^$]+\$\$|\$[^$\n]+\$/g
const notation = /`([^`\n]+)`|\b(?:data\/)?[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b|\b(?:float(?:16|32|64)|int(?:8|16|32|64))\b|\[(?:[A-Za-z0-9_]+(?:\s*,\s*[A-Za-z0-9_]+)*)?\]/g
function notationParts (text, result) {
  let cursor = 0
  for (const match of text.matchAll(notation)) {
    if (match.index > cursor) result.push({ text: text.slice(cursor, match.index), code: false })
    result.push({ text: match[1] ?? match[0], code: true })
    cursor = match.index + match[0].length
  }
  if (cursor < text.length) result.push({ text: text.slice(cursor), code: false })
}
const parts = computed(() => {
  const result = []
  let cursor = 0
  for (const match of source.value.matchAll(math)) {
    notationParts(source.value.slice(cursor, match.index), result)
    result.push({ text: match[0], code: false })
    cursor = match.index + match[0].length
  }
  notationParts(source.value.slice(cursor), result)
  return result
})
</script>
