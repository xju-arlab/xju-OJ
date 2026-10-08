<template>
  <span class="studio-statement-text"><template v-for="(part, index) in parts" :key="index"><code v-if="part.code">{{ part.text }}</code><template v-else>{{ part.text }}</template></template></span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ text: { type: String, default: '' } })
// Keep the statement as text. Emphasize code notation without interpreting HTML
// or changing the source used for notebook exports and evaluation.
const parts = computed(() => {
  const source = typeof props.text === 'string' ? props.text : ''
  const notation = /`([^`\n]+)`|\b(?:data\/)?[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b|\b(?:float(?:16|32|64)|int(?:8|16|32|64))\b|\[(?:[A-Za-z0-9_]+(?:\s*,\s*[A-Za-z0-9_]+)*)?\]/g
  const result = []
  let cursor = 0
  for (const match of source.matchAll(notation)) {
    if (match.index > cursor) result.push({ text: source.slice(cursor, match.index), code: false })
    result.push({ text: match[1] ?? match[0], code: true })
    cursor = match.index + match[0].length
  }
  if (cursor < source.length) result.push({ text: source.slice(cursor), code: false })
  return result
})
</script>
