<template>
  <span :class="['evaluation-status', { 'evaluation-inline': inline }]" :data-status="record.status" :aria-label="label">
    <template v-if="record.type === 'challenge' && record.status === 'SCORED'">
      <span class="judge-status-badge is-success evaluation-score-pill"><span>公榜</span><strong>{{ score(record.publicScore) }}</strong><small v-if="finite(record.publicScore)">分</small></span>
      <span v-if="record.privatePublished" class="judge-status-badge is-success evaluation-score-pill private"><span>私榜</span><strong>{{ score(record.privateScore) }}</strong><small v-if="finite(record.privateScore)">分</small></span>
      <span v-else class="evaluation-private"><LockKeyhole :size="10" />私榜未公布</span>
    </template>
    <template v-else><span v-if="detail" class="evaluation-detail">{{ detail }}</span><span :class="['judge-status-badge', 'evaluation-state', 'is-' + tone]">{{ label }}</span></template>
  </span>
</template>
<script setup>
import { computed } from 'vue'
import { LockKeyhole } from 'lucide-vue-next'
const props = defineProps({ record: { type: Object, required: true }, inline: Boolean })
const finite = value => typeof value === 'number' && Number.isFinite(value)
const score = value => finite(value) ? value.toFixed(1) : '待返回'
const labels = { PENDING: '排队中', JUDGING: '评测中', TRAINING: '训练中', SCORING: '评分中', RUNNING: '运行中', SUCCEEDED: '运行完成', CANCELLED: '已取消', COMPILE_ERROR: '编译错误', RUNTIME_ERROR: '运行失败', TIME_LIMIT: '超时', MEMORY_LIMIT: '内存超限', SYSTEM_ERROR: '系统错误', FAILED: '评测失败' }
const label = computed(() => {
  const item = props.record
  if (item.status === 'SCORED' && item.type === 'challenge') return '公榜 ' + score(item.publicScore) + ' 分；' + (item.privatePublished ? '私榜 ' + score(item.privateScore) + ' 分' : '私榜未公布')
  if (item.status === 'ACCEPTED') return item.type === 'model' ? '模型达标' : '全部通过'
  if (item.status === 'WRONG_ANSWER') return item.type === 'model' ? '未达标' : '未通过'
  if (item.status === 'PARTIAL') return '部分通过'
  return labels[item.status] || '状态待确认'
})
const detail = computed(() => {
  const item = props.record
  if (item.type === 'model' && ['ACCEPTED', 'WRONG_ANSWER', 'PARTIAL'].includes(item.status) && finite(item.accuracy)) return 'Accuracy ' + (item.accuracy * 100).toFixed(1) + '%'
  return ''
})
const tone = computed(() => {
  const status = props.record.status
  if (['ACCEPTED', 'SUCCEEDED'].includes(status)) return 'success'
  if (['WRONG_ANSWER', 'FAILED', 'RUNTIME_ERROR', 'SYSTEM_ERROR', 'TIME_LIMIT', 'MEMORY_LIMIT', 'CANCELLED'].includes(status)) return 'error'
  if (['PENDING', 'COMPILE_ERROR'].includes(status)) return 'warning'
  return 'info'
})
</script>
<style lang="less" scoped>
@import "@/styles/judge-status.less";
.evaluation-status { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; line-height: 1.5; }
.evaluation-inline { flex: none; flex-wrap: nowrap; white-space: nowrap; }.evaluation-inline .evaluation-private { order: -1; }
.judge-status-badge.is-neutral { color: var(--color-text-muted); background: var(--color-bg-subtle); animation: none; will-change: auto; }
.evaluation-detail, .evaluation-private { color: var(--color-text-faint); font-size: 11px; }.evaluation-private { display: inline-flex; align-items: center; gap: 3px; }
.evaluation-score-pill { gap: 6px; }
.evaluation-score-pill > span { font-size: 11px; }.evaluation-score-pill strong { font: 650 13px var(--font-mono); }.evaluation-score-pill small { font-size: 10px; color: inherit; }.evaluation-score-pill.private { background: var(--tag-recommend-bg); color: var(--cat-recommend); }
</style>
