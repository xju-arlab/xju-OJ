<template>
  <div class="studio-statement-block">
    <template v-for="(block, index) in blocks" :key="index">
      <component :is="block.type" v-if="block.type !== 'p'">
        <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
          <StatementText :text="item.text" />
          <ul v-if="item.children.length"><li v-for="(child, childIndex) in item.children" :key="childIndex"><StatementText :text="child" /></li></ul>
        </li>
      </component>
      <p v-else><StatementText :text="block.text" /></p>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import StatementText from './StatementText.vue'

const props = defineProps({ text: { type: String, default: '' }, list: Boolean })
// Plain-text structure only: each line is a paragraph, "- " lines form a bullet list,
// "1. " lines a numbered list, and indented "- " lines nest under the previous item.
// With `list`, every line is a bullet (interface listings).
const blocks = computed(() => {
  const result = []
  for (const line of (props.text || '').split('\n')) {
    if (!line.trim()) continue
    const nested = line.match(/^\s{2,}[-•]\s+(.*)$/)
    const bullet = line.match(/^\s*[-•]\s+(.*)$/) || (props.list && !nested ? [line, line.trim()] : null)
    const numbered = line.match(/^\s*\d+[.、)]\s*(.*)$/)
    const last = result[result.length - 1]
    if (nested && last && last.type !== 'p') last.items[last.items.length - 1].children.push(nested[1])
    else if (bullet || numbered) {
      const type = bullet ? 'ul' : 'ol'
      const item = { text: (bullet || numbered)[1], children: [] }
      if (last && last.type === type) last.items.push(item)
      else result.push({ type, items: [item] })
    } else result.push({ type: 'p', text: line.trim() })
  }
  return result
})
</script>
