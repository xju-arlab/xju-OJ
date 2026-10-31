<template>
  <div class="ai-studio"><div class="studio-dialog-overlay" @click.self="emit('close')" @keydown.esc="emit('close')">
    <section class="studio-dialog ai-submission-dialog" role="dialog" aria-modal="true" aria-label="提交详情">
      <header class="ai-submission-head">
        <div><h2>{{ problem.id }} · {{ problem.title }}</h2><p>{{ record?.user ? record.user.username + (record.user.realName ? '（' + record.user.realName + '）' : '') : '我的提交' }}<template v-if="record"> · {{ formatDate(record.createdAt) }}（北京时间）</template></p></div>
        <button class="studio-icon-button" aria-label="关闭" @click="emit('close')"><X :size="16" /></button>
      </header>
      <p v-if="error" role="alert" class="studio-error">{{ error }}</p>
      <p v-else-if="!record" class="studio-footnote">加载中…</p>
      <template v-else>
        <div class="ai-submission-status"><EvaluationStatus :record="record" /><span v-if="Number.isFinite(record.publicScore)">{{ record.publicScore }} / 100</span></div>
        <p v-if="record.message" class="studio-evaluation-message">{{ record.message }}</p>
        <template v-if="Array.isArray(record.payload?.cells)">
          <figure v-for="(cell, index) in record.payload.cells" :key="index" class="ai-submission-cell"><figcaption>单元格 {{ index + 1 }}</figcaption><pre><code>{{ cell }}</code></pre></figure>
        </template>
        <ol v-else-if="questions.length" class="ai-submission-answers">
          <li v-for="question in questions" :key="question.id">
            <StatementText class="ai-submission-prompt" :text="question.prompt" />
            <p class="ai-submission-answer">{{ answerText(question) }}</p>
            <p v-if="result[question.id]" class="ai-submission-key"><strong>{{ result[question.id].earned ?? '待评' }} / {{ result[question.id].points }} 分</strong><span v-if="question.kind !== 'text'">正确答案：{{ answerText(question, result[question.id].answer) }}</span><span v-else-if="!reviewing">参考要点：{{ result[question.id].rubric }}</span></p>
            <label v-if="reviewing && review[question.id]" class="ai-submission-score">评分（满分 {{ review[question.id].points }}）<input v-model.number="scores[question.id]" type="number" min="0" :max="review[question.id].points" step="0.5" /><small>参考要点：{{ review[question.id].rubric }}</small></label>
          </li>
        </ol>
        <div v-if="reviewing" class="studio-dialog-actions"><span v-if="reviewInfo?.review" class="studio-footnote">已由 {{ reviewInfo.review.reviewer }} 评阅，可重新评分</span><button class="studio-button primary" :disabled="saving" @click="grade">{{ saving ? '保存中…' : '提交评分' }}</button></div>
      </template>
    </section>
  </div></div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { X } from 'lucide-vue-next'
import { formatDate } from './studio'
import { request, studioApi } from './api'
import EvaluationStatus from './EvaluationStatus.vue'
import StatementText from './StatementText.vue'
import './studio.less'

const props = defineProps({ id: { type: String, required: true }, problem: { type: Object, required: true }, contestId: { type: String, default: '' }, canReview: Boolean })
const emit = defineEmits(['close', 'graded'])
const record = ref(null); const quiz = ref(null); const reviewInfo = ref(null); const scores = ref({}); const error = ref(''); const saving = ref(false)
const questions = computed(() => quiz.value?.questions || [])
const result = computed(() => Object.fromEntries((record.value?.breakdown || []).map(item => [item.id, item])))
const review = computed(() => Object.fromEntries((reviewInfo.value?.questions || []).map(item => [item.id, item])))
const reviewing = computed(() => Boolean(props.canReview && reviewInfo.value?.questions?.length && !['SUPERSEDED', 'CANCELLED'].includes(record.value?.status)))

function answerText (question, given) {
  const value = given !== undefined ? given : record.value.payload?.answers?.[question.id]
  if (value === null || value === undefined || value === '') return '未作答'
  if (question.kind === 'single') return question.options?.[value] ?? String(value)
  if (question.kind === 'multiple') return value.map(index => question.options?.[index] ?? index).join('；')
  if (question.kind === 'order') return value.map((index, position) => (position + 1) + '. ' + (question.options?.[index] ?? index)).join('  ')
  return String(value) + (question.unit ? ' ' + question.unit : '')
}
async function load () {
  error.value = ''
  try {
    record.value = await studioApi('jobs', 'get', { id: props.id })
    if (record.value.type === 'quiz') {
      const detail = await studioApi('problems', 'get', { problem_id: props.problem.id, ...(props.contestId ? { contest_id: props.contestId } : {}) })
      quiz.value = detail.quiz
      if (props.canReview) {
        reviewInfo.value = await request('admin/ai/reviews', 'get', { id: props.id })
        scores.value = Object.fromEntries(reviewInfo.value.questions.map(item => [item.id, reviewInfo.value.review?.scores?.[item.id] ?? null]))
      }
    }
  } catch (failure) { error.value = failure.message }
}
async function grade () {
  saving.value = true; error.value = ''
  try {
    await request('admin/ai/reviews', 'post', { id: props.id, scores: scores.value })
    await load()
    emit('graded')
  } catch (failure) { error.value = failure.message } finally { saving.value = false }
}
onMounted(load)
</script>
<style lang="less" scoped>
.ai-submission-dialog { width: 760px; }
.ai-submission-head { display: flex; justify-content: space-between; gap: 12px; }.ai-submission-head h2 { font-size: 17px; }.ai-submission-head p { margin-top: 4px; font-size: 12px; color: var(--color-text-muted); }
.ai-submission-status { display: flex; align-items: center; gap: 10px; margin: 16px 0 8px; font: 12px var(--font-mono); }
.ai-submission-cell { margin: 12px 0 0; }.ai-submission-cell figcaption { font-size: 11px; color: var(--color-text-faint); margin-bottom: 4px; }
.ai-submission-cell pre { margin: 0; padding: 10px 12px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-bg-subtle); font: 12px/1.6 var(--font-mono); white-space: pre-wrap; overflow-wrap: anywhere; }
.ai-submission-answers { margin: 14px 0 0; padding-left: 20px; }.ai-submission-answers li { margin-bottom: 14px; font-size: 13px; }
.ai-submission-answer { margin-top: 6px; padding: 8px 10px; border-radius: 4px; background: var(--color-bg-subtle); white-space: pre-wrap; overflow-wrap: anywhere; }
.ai-submission-key { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 6px; font-size: 12px; color: var(--color-text-muted); white-space: pre-wrap; }.ai-submission-key strong { color: var(--color-text); font-family: var(--font-mono); }
.ai-submission-score { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; }.ai-submission-score input { width: 90px; padding: 5px 8px; border: 1px solid var(--line-strong); border-radius: 4px; }.ai-submission-score small { flex-basis: 100%; color: var(--color-text-muted); }
.studio-dialog-actions { align-items: center; }
</style>
