<template>
  <component :is="presentation.icon" :class="['evaluation-icon', 'is-' + presentation.tone]" :size="14" :stroke-width="1.8" aria-hidden="true" />
</template>

<script setup>
import { computed } from 'vue'
import { Check, Circle, CircleAlert, LoaderCircle, X } from 'lucide-vue-next'

const props = defineProps({ status: { type: String, required: true } })
const presentation = computed(() => {
  if (['PENDING', 'RUNNING', 'JUDGING', 'TRAINING', 'SCORING'].includes(props.status)) return { icon: LoaderCircle, tone: 'pending' }
  if (['ACCEPTED', 'SCORED', 'SUCCEEDED'].includes(props.status)) return { icon: Check, tone: 'success' }
  if (['WRONG_ANSWER', 'FAILED', 'COMPILE_ERROR', 'RUNTIME_ERROR', 'TIME_LIMIT', 'MEMORY_LIMIT', 'SYSTEM_ERROR', 'CANCELLED'].includes(props.status)) return { icon: X, tone: 'error' }
  if (props.status === 'PARTIAL') return { icon: CircleAlert, tone: 'partial' }
  return { icon: Circle, tone: 'neutral' }
})
</script>

<style scoped>
.evaluation-icon { display: block; flex: none; }
.is-success { color: var(--cat-tools); }
.is-error { color: var(--cat-research); }
.is-pending, .is-partial { color: #b88a16; }
.is-neutral { color: var(--color-text-faint); }
.is-pending { animation: evaluation-icon-spin 1.4s linear infinite; }
@keyframes evaluation-icon-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .is-pending { animation: none; } }
</style>
