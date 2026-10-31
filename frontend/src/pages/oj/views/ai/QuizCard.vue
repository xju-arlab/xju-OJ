<template>
  <section class="studio-notebook studio-quiz" aria-label="作答卡">
    <div class="studio-notebook-title">
      <span class="studio-notebook-filename"><ListChecks :size="16" />作答卡 · {{ questions.length }} 题 · {{ totalPoints }} 分</span>
      <div class="studio-notebook-toolbar"><button class="studio-button compact" title="保存草稿" aria-label="保存草稿" :disabled="!authenticated" @click="save"><Save :size="14" /><span class="studio-notebook-action-label">保存草稿</span></button><button class="studio-icon-button" title="清空作答" aria-label="清空作答" :disabled="!authenticated" @click="dialog = 'reset'"><RotateCcw :size="15" /></button></div>
    </div>
    <div class="studio-notebook-scroll">
      <article v-for="(question, index) in questions" :key="question.id" :class="['studio-quiz-question', { answered: isAnswered(question) }]">
        <header class="studio-quiz-heading"><span class="studio-cell-number">{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ kindLabels[question.kind] }}</strong><span class="studio-quiz-points">{{ question.points }} 分</span></header>
        <StatementBlock class="studio-quiz-prompt" :text="question.prompt" />
        <p v-if="question.materials.length" class="studio-quiz-refs">参考材料：<span v-for="id in question.materials" :key="id">{{ materialTitle(id) }}</span></p>
        <div v-if="question.kind === 'single' || question.kind === 'multiple'" class="studio-quiz-options" :role="question.kind === 'single' ? 'radiogroup' : 'group'" :aria-label="'第 ' + (index + 1) + ' 题选项'">
          <label v-for="(option, optionIndex) in question.options" :key="optionIndex" :class="{ selected: isSelected(question, optionIndex) }">
            <input :type="question.kind === 'single' ? 'radio' : 'checkbox'" :name="question.id" :checked="isSelected(question, optionIndex)" :disabled="!authenticated" @change="choose(question, optionIndex, $event.target.checked)" />
            <span class="studio-quiz-letter">{{ letters[optionIndex] }}</span><StatementText :text="option" />
          </label>
        </div>
        <div v-else-if="question.kind === 'text'" class="studio-quiz-text">
          <textarea :value="answers[question.id] ?? ''" :maxlength="2000" rows="8" :disabled="!authenticated" :aria-label="'第 ' + (index + 1) + ' 题作答'" placeholder="在这里写出你的答案" @input="setAnswer(question.id, $event.target.value || null)" />
          <small>{{ (answers[question.id] || '').length }} / 2000 · 由老师评阅</small>
        </div>
        <div v-else-if="question.kind === 'number'" class="studio-quiz-number">
          <input type="text" inputmode="decimal" autocomplete="off" :value="numbers[question.id] ?? ''" :disabled="!authenticated" :aria-label="'第 ' + (index + 1) + ' 题数值'" placeholder="填写数值" @input="setNumber(question, $event.target.value)" />
          <span v-if="question.unit">{{ question.unit }}</span>
          <small v-if="invalid[question.id]" role="alert">请输入有效数字，例如 12.5 或 1e-3</small>
        </div>
        <div v-else class="studio-quiz-order">
          <ol><li v-for="(optionIndex, position) in orderOf(question)" :key="optionIndex"><span class="studio-quiz-letter">{{ position + 1 }}</span><StatementText :text="question.options[optionIndex]" /><button class="studio-icon-button" :disabled="!authenticated || position === 0" :aria-label="'上移：' + question.options[optionIndex]" @click="move(question, position, -1)"><ArrowUp :size="14" /></button><button class="studio-icon-button" :disabled="!authenticated || position === question.options.length - 1" :aria-label="'下移：' + question.options[optionIndex]" @click="move(question, position, 1)"><ArrowDown :size="14" /></button></li></ol>
          <button v-if="!isAnswered(question)" class="studio-text-button" :disabled="!authenticated" @click="setAnswer(question.id, orderOf(question))"><Check :size="13" />确认当前顺序</button>
        </div>
      </article>
      <p v-if="error" role="alert" class="studio-error">{{ error }}</p>
    </div>
    <div class="studio-notebook-status"><span aria-live="polite">已作答 {{ answeredCount }} / {{ questions.length }}</span><span v-if="attemptText">{{ attemptText }}</span></div>
    <div class="studio-submit-dock">
      <div class="studio-submit-feedback"><span class="studio-save-state" role="status">{{ saveStatus }}</span><div v-if="latest" class="studio-last-evaluation"><span>最近提交</span><EvaluationStatus :record="latest" /></div></div>
      <button class="studio-button primary" :disabled="submitting || !authenticated || exhausted" @click="dialog = 'submit'"><Send :size="15" />{{ submitting ? '提交中…' : exhausted ? '提交次数已用完' : '提交作答' }}</button>
    </div>
    <div v-if="dialog" class="studio-dialog-overlay" @click.self="dialog = ''" @keydown.esc="dialog = ''">
      <section class="studio-dialog" role="dialog" aria-modal="true" :aria-label="dialogTitle">
        <h2>{{ dialogTitle }}</h2>
        <template v-if="dialog === 'submit'"><p>已作答 {{ answeredCount }} / {{ questions.length }} 题，未作答的小题记 0 分。</p><p v-if="attemptText">{{ attemptText }}。</p></template>
        <p v-else-if="dialog === 'reset'">当前作答将全部清空。</p>
        <template v-else-if="latest"><p>{{ latest.status === 'REVIEWING' ? '客观题已判分，主观题等待老师评阅，评阅后计入成绩。' : '本次得分 ' + (latest.publicScore ?? '—') + ' / 100。' }}</p><p class="studio-footnote">{{ latest.problemId }} · {{ latest.id.slice(0, 8) }} · {{ formatDate(latest.createdAt) }}（北京时间）</p></template>
        <div class="studio-dialog-actions">
          <button class="studio-button" @click="dialog = ''">{{ dialog === 'result' ? '关闭' : '取消' }}</button>
          <button v-if="dialog === 'submit'" class="studio-button primary" @click="submit">确认提交</button>
          <button v-else-if="dialog === 'reset'" class="studio-button primary" @click="reset">清空</button>
          <router-link v-else class="studio-button primary" :to="{ name: 'ai-submissions' }">查看提交记录</router-link>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, Check, ListChecks, RotateCcw, Save, Send } from 'lucide-vue-next'
import store from '@/store'
import storage from '@/utils/storage'
import { formatDate } from './studio'
import { studioApi } from './api'
import EvaluationStatus from './EvaluationStatus.vue'
import StatementText from './StatementText.vue'
import StatementBlock from './StatementBlock.vue'

const props = defineProps({
  problem: { type: Object, required: true },
  contestId: { type: String, default: '' },
  authenticated: { type: Boolean, default: false }
})
const kindLabels = { single: '单选题', multiple: '多选题', number: '数值题', order: '排序题', text: '主观题' }
const letters = 'ABCDEFGHIJKL'
const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/
const answers = ref({}); const numbers = ref({}); const invalid = ref({})
const saveStatus = ref('尚未作答'); const error = ref(''); const latest = ref(null)
const submitting = ref(false); const dialog = ref(''); const attemptsUsed = ref(0)
const questions = computed(() => props.problem.quiz?.questions || [])
const totalPoints = computed(() => questions.value.reduce((sum, question) => sum + question.points, 0))
const isAnswered = question => answers.value[question.id] != null && !(Array.isArray(answers.value[question.id]) && !answers.value[question.id].length)
const answeredCount = computed(() => questions.value.filter(isAnswered).length)
const official = computed(() => !!props.contestId && !props.problem.practice)
const exhausted = computed(() => official.value && !!props.problem.maxAttempts && attemptsUsed.value >= props.problem.maxAttempts)
const attemptText = computed(() => official.value && props.problem.maxAttempts ? `比赛中本题最多提交 ${props.problem.maxAttempts} 次，已提交 ${attemptsUsed.value} 次` : '')
const dialogTitle = computed(() => ({ submit: '提交作答？', reset: '清空作答？', result: '作答已提交' })[dialog.value] || '')
const materialTitle = id => {
  const index = (props.problem.quiz?.materials || []).findIndex(item => item.id === id)
  return index < 0 ? id : props.problem.quiz.materials[index].title || '材料 ' + (index + 1)
}
const isSelected = (question, option) => question.kind === 'single' ? answers.value[question.id] === option : (answers.value[question.id] || []).includes(option)
const orderOf = question => Array.isArray(answers.value[question.id]) ? answers.value[question.id] : question.options.map((_, index) => index)

let context = null; let timer; let generation = 0
function backup (ctx) { return storage.set(ctx.key, { answers: { ...ctx.answers }, revision: ctx.revision }) }
async function persist (ctx) {
  if (!ctx || !ctx.dirty) return true
  if (ctx.userId !== store.getters.user.id) return false
  const backedUp = backup(ctx)
  if (!props.authenticated || ctx.conflict) return false
  if (ctx.saving) { const saved = await ctx.saving; return saved && ctx.dirty ? persist(ctx) : saved }
  const captured = { ...ctx.answers }
  ctx.saving = studioApi('draft', 'put', { ...ctx.scope, answers: captured, revision: ctx.revision })
    .then(result => {
      ctx.revision = result.revision
      ctx.dirty = JSON.stringify(ctx.answers) !== JSON.stringify(captured)
      backup(ctx)
      if (context === ctx) saveStatus.value = ctx.dirty ? '保存中…' : '已保存至云端'
      return true
    }).catch(failure => {
      if (failure.code === 'draft-conflict') ctx.conflict = true
      if (context === ctx) { saveStatus.value = backedUp ? '云端保存失败 · 本机备份已保留' : '保存失败'; error.value = failure.message }
      return false
    }).finally(() => { ctx.saving = null })
  return ctx.saving
}
async function save () { clearTimeout(timer); return persist(context) }
function setAnswer (id, value) {
  answers.value = { ...answers.value, [id]: value }
  if (!context) return
  context.answers = { ...answers.value }; context.dirty = true
  saveStatus.value = '保存中…'; backup(context)
  clearTimeout(timer); timer = setTimeout(save, 800)
}
function choose (question, option, checked) {
  if (question.kind === 'single') { setAnswer(question.id, option); return }
  const current = new Set(answers.value[question.id] || [])
  if (checked) current.add(option); else current.delete(option)
  setAnswer(question.id, current.size ? [...current].sort((a, b) => a - b) : null)
}
function setNumber (question, text) {
  numbers.value = { ...numbers.value, [question.id]: text }
  const value = text.trim()
  const valid = !value || (NUMBER.test(value) && Number.isFinite(Number(value)) && Math.abs(Number(value)) <= 1e15)
  invalid.value = { ...invalid.value, [question.id]: !valid }
  setAnswer(question.id, value && valid ? Number(value) : null)
}
function move (question, position, delta) {
  const order = [...orderOf(question)]
  const target = position + delta
  ;[order[position], order[target]] = [order[target], order[position]]
  setAnswer(question.id, order)
}
function fill (values) {
  const clean = {}
  for (const question of questions.value) clean[question.id] = values?.[question.id] ?? null
  answers.value = clean
  numbers.value = Object.fromEntries(questions.value.filter(question => question.kind === 'number' && clean[question.id] != null)
    .map(question => [question.id, String(clean[question.id])]))
  invalid.value = {}
}
async function load () {
  const current = ++generation
  if (context?.dirty) persist(context)
  context = null; clearTimeout(timer)
  error.value = ''; latest.value = null; dialog.value = ''; submitting.value = false
  attemptsUsed.value = props.problem.attemptsUsed || 0
  fill({})
  const scope = { problem_id: props.problem.id, contest_id: props.contestId }
  if (!props.authenticated) { saveStatus.value = '登录后可作答与提交'; return }
  try {
    const draft = await studioApi('draft', 'get', scope)
    if (current !== generation) return
    const key = 'problemAnswers_aiQuiz_v1_' + JSON.stringify([store.getters.user.id, scope.contest_id, scope.problem_id])
    const local = storage.get(key)
    const recover = local && local.revision === draft.revision && local.answers && typeof local.answers === 'object'
    fill(recover ? local.answers : draft.answers)
    context = { key, scope, userId: store.getters.user.id, answers: { ...answers.value }, revision: draft.revision, dirty: !!recover, conflict: false, saving: null, pending: null }
    saveStatus.value = recover ? '已恢复本机备份' : draft.revision ? '已加载云端草稿' : '尚未作答'
    const records = await studioApi('jobs', 'get', { ...scope, limit: 1 })
    if (current === generation) latest.value = records.results[0] || null
  } catch (failure) { if (current === generation) error.value = failure.message }
}
async function submit () {
  if (!context || submitting.value) return
  const ctx = context; const current = generation
  dialog.value = ''; error.value = ''; submitting.value = true
  const payload = { ...ctx.scope, kind: 'evaluation', answers: { ...answers.value } }
  const signature = JSON.stringify(payload)
  // Retrying the same answers reuses the UUID, so a lost response never counts as two attempts.
  if (!ctx.pending || ctx.pending.signature !== signature) ctx.pending = { id: crypto.randomUUID(), signature }
  try {
    await save()
    const record = await studioApi('jobs', 'post', { id: ctx.pending.id, ...payload })
    ctx.pending = null
    if (current !== generation) return
    latest.value = record
    if (record.official) attemptsUsed.value += 1
    dialog.value = 'result'
  } catch (failure) { if (current === generation) error.value = failure.message }
  finally { if (current === generation) submitting.value = false }
}
function reset () { dialog.value = ''; fill({}); if (context) { context.answers = { ...answers.value }; context.dirty = true; save() } }
watch(() => [props.problem.id, props.contestId, props.authenticated, store.getters.user.id], load, { immediate: true })
onBeforeUnmount(() => { generation++; if (context?.dirty) persist(context); clearTimeout(timer) })
</script>
