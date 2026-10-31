<template>
  <Panel title="主观题评阅">
    <div class="review-tools">
      <el-radio-group v-model="status" @change="load"><el-radio-button value="pending">待评阅</el-radio-button><el-radio-button value="done">已评阅</el-radio-button></el-radio-group>
      <el-input v-model="contestId" placeholder="比赛 ID（可选）" clearable class="review-contest" @change="load" />
      <span class="review-total">共 {{ total }} 份</span>
    </div>
    <p v-if="error" role="alert" class="review-error">{{ error }}</p>
    <p v-if="!items.length && !loading" class="review-empty">{{ status === 'pending' ? '没有待评阅的作答。' : '还没有评阅记录。' }}</p>
    <article v-for="item in items" :key="item.id" class="review-item">
      <header><strong>{{ item.problemId }} · {{ item.title }}</strong><span>{{ item.username }}<template v-if="item.realName">（{{ item.realName }}）</template></span><span>{{ formatDate(item.createdAt) }}</span><span v-if="item.contestId">比赛 {{ item.contestId }}{{ item.official ? '' : ' · 非正式' }}</span><span>客观题 {{ item.objectiveScore }} 分</span><span v-if="item.publicScore != null">总分 {{ item.publicScore }}</span></header>
      <section v-for="question in item.questions" :key="question.id" class="review-question">
        <StatementBlock class="review-prompt" :text="question.prompt" />
        <div class="review-rubric"><b>评分要点</b><StatementBlock :text="question.rubric" /></div>
        <pre class="review-answer">{{ question.answer || '（未作答）' }}</pre>
        <div v-if="item.status === 'REVIEWING' && question.answer" class="review-score">得分 <el-input-number v-model="scores[item.id][question.id]" :min="0" :max="question.points" :step="1" /> / {{ question.points }}</div>
        <div v-else class="review-score">得分 {{ item.review?.scores?.[question.id] ?? 0 }} / {{ question.points }}<template v-if="item.review"> · {{ item.review.reviewer }}</template></div>
      </section>
      <el-button v-if="item.status === 'REVIEWING'" type="primary" :loading="saving === item.id" @click="submit(item)">提交评分</el-button>
    </article>
    <el-button v-if="items.length < total" :loading="loading" @click="load(true)">加载更多</el-button>
  </Panel>
</template>
<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { request } from '@oj/views/ai/api'
import { formatDate } from '@oj/views/ai/studio'
import StatementBlock from '@oj/views/ai/StatementBlock.vue'

const status = ref('pending'); const contestId = ref(''); const items = ref([]); const total = ref(0)
const scores = ref({}); const error = ref(''); const loading = ref(false); const saving = ref('')
let generation = 0
async function load (more = false) {
  const current = ++generation
  loading.value = true; error.value = ''
  try {
    const params = { status: status.value, offset: more === true ? items.value.length : 0, limit: 20 }
    if (contestId.value) params.contest_id = String(contestId.value).trim()
    const result = await request('admin/ai/reviews', 'get', params)
    if (current !== generation) return
    for (const item of result.results) scores.value[item.id] ??= Object.fromEntries(item.questions.filter(q => q.answer).map(q => [q.id, 0]))
    items.value = more === true ? [...items.value, ...result.results] : result.results
    total.value = result.total
  } catch (failure) { if (current === generation) error.value = failure.message }
  finally { if (current === generation) loading.value = false }
}
async function submit (item) {
  saving.value = item.id; error.value = ''
  try {
    const graded = await request('admin/ai/reviews', 'post', { id: item.id, scores: scores.value[item.id] })
    items.value = items.value.filter(entry => entry.id !== item.id); total.value -= 1
    ElMessage.success(`已评阅：${graded.username} · ${graded.problemId} 总分 ${graded.publicScore}`)
  } catch (failure) { error.value = failure.message }
  finally { saving.value = '' }
}
load()
onBeforeUnmount(() => { generation++ })
</script>
<style scoped>
.review-tools { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }.review-contest { width: 180px; }
.review-total, .review-empty { color: var(--color-text-muted); font-size: 13px; }.review-error { color: var(--oj-danger); }
.review-item { padding: 18px 0; border-top: 1px solid var(--color-border); }
.review-item header { display: flex; flex-wrap: wrap; gap: 14px; align-items: baseline; margin-bottom: 12px; color: var(--color-text-muted); font-size: 12px; }
.review-item header strong { color: var(--color-text); font-size: 14px; }
.review-question { margin-bottom: 14px; }.review-prompt { font-weight: 550; }
.review-rubric { margin: 8px 0; padding: 8px 12px; border-left: 3px solid var(--color-border); color: var(--color-text-muted); font-size: 13px; }
.review-answer { margin: 0; padding: 12px 14px; border-radius: var(--radius-sm); background: var(--color-bg-subtle); white-space: pre-wrap; overflow-wrap: anywhere; font: 14px/1.75 var(--font-sans); }
.review-score { margin-top: 8px; font-size: 13px; }
</style>
