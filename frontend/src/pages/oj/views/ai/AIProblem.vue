<template>
  <div class="ai-studio ai-problem-page">
    <div v-if="!problem" class="studio-empty"><h2>{{ loading ? '加载中…' : '题目暂不可用' }}</h2><p role="alert">{{ error }}</p><router-link class="studio-button" :to="{ name: 'ai-studio' }">返回题库</router-link></div>
    <template v-else>
      <div class="studio-workspace">
        <section class="studio-statement">
          <header class="studio-problem-header">
            <div class="studio-problem-heading">
              <div class="studio-problem-kicker"><small>Problem {{ problem.id }}</small><router-link class="studio-back-link" :to="contestId ? { name: 'ai-contest', params: { contestID: contestId } } : { name: 'ai-studio' }"><ArrowLeft :size="14" />{{ contestId ? '返回比赛' : '题库' }}</router-link></div>
              <div class="studio-problem-title-line"><h1>{{ problem.title }}</h1><div class="studio-problem-meta"><span :class="['studio-badge', categoryFor(problem.type).tone]">{{ categoryFor(problem.type).name }}</span><span>{{ problem.metric }}</span><span>{{ contestId && !problem.practice ? '比赛作答' : '自主练习' }}</span></div></div>
            </div>
          </header>
          <nav class="studio-tabs small" aria-label="题目资料"><button v-for="tab in infoTabs" :key="tab.id" :class="{ active: infoTab === tab.id }" @click="infoTab = tab.id">{{ tab.name }}</button></nav>
          <div v-if="infoTab === 'description'" class="studio-prose">
            <h2>任务目标</h2>
            <p><StatementText :text="problem.objective" /></p>
            <h2>实现要求</h2>
            <ol><li v-for="item in problem.requirements" :key="item"><StatementText :text="item" /></li></ol>
            <h2>接口约定</h2>
            <pre class="studio-signature"><code>{{ problem.signature }}</code></pre>
            <template v-if="problem.inputSpec">
              <h2>输入</h2>
              <div class="studio-io-description"><p v-for="(line, index) in statementLines(problem.inputSpec)" :key="index"><StatementText :text="line" /></p></div>
            </template>
            <template v-if="problem.outputSpec">
              <h2>输出</h2>
              <div class="studio-io-description"><p v-for="(line, index) in statementLines(problem.outputSpec)" :key="index"><StatementText :text="line" /></p></div>
            </template>
          </div>
          <div v-else-if="infoTab === 'data'" class="studio-prose">
            <h2>数据说明</h2><p><StatementText :text="problem.data" /></p>
            <div class="studio-files">
              <div v-for="name in problem.files" :key="name" class="studio-file-row"><FileCode :size="18" /><strong>{{ name }}</strong><a class="studio-text-button" :href="dataUrl(name)"><Download :size="14" />下载</a></div>
              <div class="studio-file-row"><NotebookPen :size="18" /><div><strong>{{ problem.id }}.ipynb</strong><small>题目说明、代码框架与公开样例</small></div><button class="studio-text-button" @click="exportNotebook"><Download :size="14" />下载</button></div>
            </div>
          </div>
          <div v-else-if="infoTab === 'evaluation'" class="studio-prose"><h2>评分说明</h2><p><StatementText :text="problem.evaluation" /></p><dl class="studio-facts"><div><dt>赛制</dt><dd>AI · {{ $t('m.AI_Evaluation') }}</dd></div><div><dt>本题分值</dt><dd>{{ problem.points }} 分</dd></div><div><dt>评测指标</dt><dd>{{ problem.metric }}</dd></div></dl></div>
          <ProblemRanking v-else :problem-id="problem.id" :contest-id="contestId" :authenticated="authenticated" />
          <div class="studio-problem-pagination"><router-link v-if="previous" :to="problemRoute(previous.id)"><ArrowLeft :size="14" />上一题</router-link><span v-else></span><router-link v-if="next" :to="problemRoute(next.id)">下一题<ArrowRight :size="14" /></router-link></div>
        </section>
        <section class="studio-notebook" aria-label="Notebook 作答区">
          <div class="studio-notebook-title">
            <span class="studio-notebook-filename"><NotebookPen :size="16" />{{ problem.id }}.ipynb</span>
            <div class="studio-notebook-toolbar"><button :class="['studio-button', 'compact', { 'is-running': running }]" :disabled="running || !authenticated" :aria-busy="running" :title="running ? runLabel : '运行全部'" aria-label="运行全部" @click="runTask('notebook')"><LoaderCircle v-if="running" class="studio-spin" :size="14" /><Play v-else :size="14" /><span class="studio-notebook-action-label">{{ running ? runLabel : '运行全部' }}</span></button><button class="studio-button compact" title="保存草稿" aria-label="保存草稿" @click="save"><Save :size="14" /><span class="studio-notebook-action-label">保存草稿</span></button><button class="studio-button compact" title="导出" aria-label="导出" @click="exportNotebook"><Download :size="14" /><span class="studio-notebook-action-label">导出</span></button><button class="studio-icon-button" :disabled="running" title="重置为题目框架" aria-label="重置题目框架" @click="showReset = true"><RotateCcw :size="15" /></button></div>
          </div>
          <div class="studio-notebook-scroll">
            <article v-for="(code, index) in cells" :key="activeKey + index" :class="['studio-cell', 'cell-' + cellStatus(index).toLowerCase()]" :data-cell-state="cellStatus(index)" @keydown.shift.enter.capture.prevent.stop="runCell(index, true)">
              <div class="studio-cell-heading"><span class="studio-cell-number">{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ cellTitles[index] || '代码单元格' }}</strong><span v-if="cellStatus(index) !== 'IDLE'" class="studio-cell-state"><Check v-if="cellStatus(index) === 'SUCCEEDED'" :size="12" /><X v-else-if="cellStatus(index) === 'ERROR'" :size="12" />{{ cellLabels[cellStatus(index)] }}</span><span class="studio-cell-language">Python</span><button class="studio-icon-button studio-cell-run" :disabled="running || !authenticated" :aria-label="'运行第 ' + (index + 1) + ' 个单元格'" title="运行当前单元格 · Shift+Enter 运行并前进" @click="runCell(index)"><LoaderCircle v-if="cellStatus(index) === 'RUNNING'" class="studio-spin" :size="14" /><Play v-else :size="14" /></button></div>
              <div class="studio-cell-input"><span class="studio-cell-prompt">[{{ cellStatus(index) === 'RUNNING' ? '*' : outputs[index]?.execution_count ?? ' ' }}]</span><CodeMirror :ref="editor => { cellEditors[index] = editor }" :model-value="code" mode="text/x-python" @update:model-value="value => updateCell(index, value)" /></div>
              <div v-if="hasOutput(index)" class="studio-cell-output"><pre>{{ outputs[index].text }}</pre><img v-for="(png, imageIndex) in outputs[index].png" :key="imageIndex" :src="'data:image/png;base64,' + png" alt="单元格输出图表" /></div>
            </article>
            <div v-if="problem.type === 'challenge'" class="studio-notebook-notice">
              <div class="studio-prediction-heading"><FileCode :size="16" /><strong>预测结果 CSV</strong><label class="studio-button compact studio-file-picker">选择文件<input type="file" accept=".csv,text/csv" aria-label="上传预测结果 CSV" @change="readPredictions" /></label></div>
              <div v-if="predictionName" class="studio-prediction-file"><span>{{ predictionName }}</span><button v-if="predictions" class="studio-text-button" @click="download('predictions.csv', predictions, 'text/csv')"><Download :size="14" />下载</button></div>
              <p v-else>上传预测文件，或运行代码生成 predictions.csv。</p>
            </div><p v-if="error" role="alert" class="studio-error">{{ error }}</p><button v-if="oldBackup" class="studio-text-button" @click="exportBackup">导出旧的本机备份</button>
          </div>
          <div class="studio-notebook-status"><span class="studio-run-state" aria-live="polite">{{ runState ? runLabel : 'Notebook · ' + cells.length + ' 个代码单元格' }}</span><span :class="['studio-kernel', { 'is-busy': running }]"><span></span>Python 3 · {{ running ? '忙碌' : '空闲' }}</span><span>Shift+Enter 运行并前进</span></div>
          <div class="studio-submit-dock">
            <div class="studio-submit-feedback"><span class="studio-save-state" role="status">{{ saveStatus }}</span><div v-if="latestEvaluation" class="studio-last-evaluation"><span>最近评测</span><EvaluationStatus :record="latestEvaluation" /></div></div>
            <button class="studio-button primary" :disabled="submitting || !authenticated" @click="runTask('evaluation')"><Send :size="15" />{{ submitting ? '提交中…' : '提交评测' }}</button>
          </div>
        </section>
      </div>
      <div v-if="showReset || snapshot" class="studio-dialog-overlay" @click.self="closeDialog" @keydown.esc="closeDialog"><section class="studio-dialog" role="dialog" aria-modal="true" :aria-label="showReset ? '重置框架' : '答卷已提交'"><h2>{{ showReset ? '恢复初始框架？' : '答卷已提交' }}</h2><p>{{ showReset ? '当前题目的草稿将恢复为初始框架。' : '答卷已保存，评测状态会自动更新。' }}</p><p v-if="snapshot" class="studio-footnote">{{ snapshot.problemId }} · {{ snapshot.id.slice(0, 8) }} · {{ formatDate(snapshot.createdAt) }}（北京时间）</p><div class="studio-dialog-actions"><button class="studio-button" @click="closeDialog">{{ showReset ? '取消' : '继续编辑' }}</button><button v-if="showReset" class="studio-button primary" @click="reset">恢复框架</button><router-link v-else class="studio-button primary" :to="{ name: 'ai-submissions' }">查看提交记录</router-link></div></section></div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, ArrowRight, Check, Download, FileCode, LoaderCircle, NotebookPen, Play, RotateCcw, Save, Send, X } from 'lucide-vue-next'
import CodeMirror from '@/shared/editors/CodeMirrorAdapter.vue'
import store from '@/store'
import storage from '@/utils/storage'
import { categoryFor, notebookFor, download, formatDate } from './studio'
import { studioApi, activeStatuses } from './api'
import EvaluationStatus from './EvaluationStatus.vue'
import ProblemRanking from './ProblemRanking.vue'
import StatementText from './StatementText.vue'
import './studio.less'

const route = useRoute()
const problem = ref(null); const loading = ref(false); const error = ref('')
const contestId = computed(() => typeof route.query.contest === 'string' ? route.query.contest : '')
const authenticated = computed(() => store.getters.isAuthenticated)
const cells = ref([]); const outputs = ref([]); const activeKey = ref(''); const saveStatus = ref('尚未修改')
const latestEvaluation = ref(null); const running = ref(false); const submitting = ref(false)
const runState = ref(''); const cellEditors = ref([])
const cellLabels = { PENDING: '等待执行', RUNNING: '运行中', SUCCEEDED: '已完成', ERROR: '运行失败', SKIPPED: '未执行' }
const cellStatus = index => outputs.value[index]?.status || (outputs.value[index]?.execution_count != null ? 'SUCCEEDED' : 'IDLE')
const hasOutput = index => !!(outputs.value[index]?.text || outputs.value[index]?.png?.length)
const runLabel = computed(() => {
  if (runState.value === 'SUBMITTING') return '正在提交…'
  if (runState.value === 'PENDING') return '排队中…'
  if (running.value) {
    const index = outputs.value.findIndex(cell => cell.status === 'RUNNING')
    if (index >= 0) return '正在运行第 ' + (index + 1) + ' 格'
    return outputs.value.some(cell => cell.status === 'PENDING') ? '正在准备内核…' : '正在收尾…'
  }
  return { SUCCEEDED: '运行完成', RUNTIME_ERROR: '运行失败', TIME_LIMIT: '运行超时', MEMORY_LIMIT: '内存超限', SYSTEM_ERROR: '运行服务异常', CANCELLED: '运行已取消', KERNEL_RESET: '内核已重启', REQUEST_FAILED: '运行未开始' }[runState.value] || 'Notebook'
})
const predictionName = ref(''); const predictions = ref('')
const oldBackup = ref(null)
const infoTab = ref('description'); const showReset = ref(false); const snapshot = ref(null)
const infoTabs = [{ id: 'description', name: '题目' }, { id: 'data', name: '数据与框架' }, { id: 'evaluation', name: '评测' }, { id: 'ranking', name: '排行' }]
const cellTitles = ['准备环境', '完成你的实现', '公开样例']
const statementLines = value => value.split(/\n+/).filter(line => line.trim())
const previous = ref(null); const next = ref(null)
const dataUrl = name => '/api/ai/file?' + new URLSearchParams({ problem_id: problem.value.id, contest_id: contestId.value, name })
const problemRoute = id => ({ name: 'ai-problem', params: { problemID: id }, query: contestId.value ? { contest: contestId.value } : {} })
let timer; let generation = 0; let context = null
const polls = new Map()
function clearPolls () { for (const timer of polls.values()) clearTimeout(timer); polls.clear() }
function kernelSession (key) {
  try { const saved = JSON.parse(sessionStorage.getItem(key + ':kernel')); if (typeof saved?.id === 'string' && /^[0-9a-f-]{36}$/.test(saved.id)) return saved } catch {}
  return { id: crypto.randomUUID(), generation: '', job: '' }
}
function saveKernel (ctx) { try { sessionStorage.setItem(ctx.key + ':kernel', JSON.stringify(ctx.kernel)) } catch {} }
function applyNotebookResult (result) {
  runState.value = result.output?.kernel_reset ? 'KERNEL_RESET' : result.status
  running.value = activeStatuses.has(result.status)
  if (Array.isArray(result.output?.cells)) outputs.value = result.output.cells
  if (result.output?.kernel_id && context) { context.kernel.generation = result.output.kernel_id; saveKernel(context) }
  if (typeof result.output?.predictions === 'string') { predictions.value = result.output.predictions; predictionName.value = 'predictions.csv（本次运行）' }
  if (result.message) error.value = result.message
}
function backup (ctx) { return storage.set(ctx.key, { cells: [...ctx.cells], revision: ctx.revision }) }
async function persist (ctx) {
  if (!ctx || !ctx.dirty) return true
  if (ctx.userId !== store.getters.user.id) return false
  const backedUp = backup(ctx)
  if (!authenticated.value || ctx.conflict) return false
  if (ctx.saving) { const saved = await ctx.saving; return saved && ctx.dirty ? persist(ctx) : saved }
  const captured = [...ctx.cells]
  ctx.saving = studioApi('draft', 'put', { ...ctx.scope, cells: captured, revision: ctx.revision })
    .then(result => {
      ctx.revision = result.revision
      ctx.dirty = JSON.stringify(ctx.cells) !== JSON.stringify(captured)
      backup(ctx)
      if (context === ctx) saveStatus.value = ctx.dirty ? '保存中…' : '已保存至云端'
      return true
    }).catch(failure => {
      if (failure.code === 'draft-conflict') ctx.conflict = true
      if (context === ctx) { saveStatus.value = backedUp ? '云端保存失败 · 本机备份已保留' : '保存失败，请立即导出'; error.value = failure.message }
      return false
    }).finally(() => { ctx.saving = null })
  return ctx.saving
}
async function save () { clearTimeout(timer); return persist(context) }
function updateCell (index, value) {
  cells.value[index] = value
  if (!context) return
  context.cells = [...cells.value]; context.dirty = true
  saveStatus.value = '保存中…'; backup(context)
  clearTimeout(timer); timer = setTimeout(save, 800)
}
async function load () {
  const current = ++generation
  const old = context
  if (old?.dirty) persist(old)
  context = null; clearTimeout(timer); clearPolls()
  problem.value = null; error.value = ''; outputs.value = []; snapshot.value = null; showReset.value = false
  infoTab.value = 'description'; loading.value = true; running.value = false; submitting.value = false
  runState.value = ''; cellEditors.value = []
  predictions.value = ''; predictionName.value = ''; previous.value = null; next.value = null
  latestEvaluation.value = null; oldBackup.value = null
  const scope = { problem_id: route.params.problemID, contest_id: contestId.value }
  try {
    const item = await studioApi('problems', 'get', scope)
    const draft = authenticated.value ? await studioApi('draft', 'get', scope) : { cells: item.cells, revision: 0 }
    if (current !== generation) return
    problem.value = item
    previous.value = item.previous ? { id: item.previous } : null
    next.value = item.next ? { id: item.next } : null
    const key = 'problemCode_aiStudio_v2_' + JSON.stringify([store.getters.user.id || 'anonymous', scope.contest_id, item.id])
    activeKey.value = key
    const local = storage.get(key)
    const recover = local && local.revision === draft.revision && Array.isArray(local.cells) && local.cells.every(cell => typeof cell === 'string')
    cells.value = recover ? [...local.cells] : [...draft.cells]
    context = { key, scope, userId: store.getters.user.id, cells: [...cells.value], revision: draft.revision, dirty: !!recover, conflict: false, saving: null, kernel: kernelSession(key) }
    saveStatus.value = recover ? '已恢复本机备份' : authenticated.value ? '已加载云端草稿' : '登录后可运行与评测'
    if (local && !recover && Array.isArray(local.cells)) {
      oldBackup.value = local.cells
      error.value = '云端草稿已更新，可以导出旧的本机备份后继续编辑。'
    }
    if (authenticated.value) {
      const records = await studioApi('jobs', 'get', { ...scope, limit: 1 })
      if (current !== generation) return
      latestEvaluation.value = records.results[0] || null
      if (latestEvaluation.value && activeStatuses.has(latestEvaluation.value.status)) poll(latestEvaluation.value.id, 'evaluation', current)
      if (context.kernel.job) {
        const run = await studioApi('jobs', 'get', { id: context.kernel.job })
        if (current !== generation) return
        if (run.kind === 'notebook' && run.problemId === item.id && String(run.contestId || '') === String(scope.contest_id || '')) {
          applyNotebookResult(run)
          if (running.value) poll(run.id, 'notebook', current)
        }
      }
    }
  } catch (failure) { if (current === generation) error.value = failure.message }
  finally { if (current === generation) loading.value = false }
}
watch(() => [route.params.problemID, contestId.value, authenticated.value, store.getters.user.id], load, { immediate: true })
onBeforeUnmount(() => { generation++; if (context?.dirty) persist(context); clearTimeout(timer); clearPolls() })
function exportNotebook () { download(problem.value.id + '.ipynb', JSON.stringify(notebookFor(problem.value, cells.value), null, 2)) }
function exportBackup () { download(problem.value.id + '-backup.ipynb', JSON.stringify(notebookFor(problem.value, oldBackup.value), null, 2)) }
function reset () { cells.value = [...problem.value.cells]; context.cells = [...cells.value]; context.dirty = true; save(); outputs.value = []; showReset.value = false }
function closeDialog () { showReset.value = false; snapshot.value = null }
async function readPredictions (event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (file.size > 1024 * 1024) { error.value = 'CSV 文件不能超过 1 MiB'; return }
  const current = generation
  const text = await file.text()
  if (current === generation) { predictions.value = text; predictionName.value = file.name }
}
function runCell (index, advance = false) {
  if (running.value || !authenticated.value) return
  runTask('notebook', index)
  if (advance) {
    if (index === cells.value.length - 1 && cells.value.length < 64) updateCell(cells.value.length, '')
    nextTick(() => cellEditors.value[index + 1]?.focus())
  }
}
async function runTask (kind, cellIndex = null) {
  if (!context || !authenticated.value || (kind === 'notebook' && running.value)) return
  const current = generation; const ctx = context
  error.value = ''
  const pendingKey = kind === 'notebook' ? 'pendingRun' : 'pendingSubmit'
  const payload = { ...ctx.scope, cells: [...cells.value], kind, ...(kind === 'evaluation' && problem.value.type === 'challenge' ? { predictions: predictions.value } : {}) }
  if (kind === 'notebook') Object.assign(payload, { kernel: ctx.kernel.id, kernel_generation: ctx.kernel.generation, cell_index: cellIndex })
  const signature = JSON.stringify(payload)
  if (!ctx[pendingKey] || ctx[pendingKey].signature !== signature) ctx[pendingKey] = { id: crypto.randomUUID(), signature }
  if (kind === 'notebook') {
    running.value = true; runState.value = 'SUBMITTING'
    outputs.value = cells.value.map((_, index) => cellIndex === null || index === cellIndex
      ? { status: 'PENDING', text: '', png: [], execution_count: null }
      : outputs.value[index] || { status: 'IDLE', text: '', png: [], execution_count: null })
  }
  else submitting.value = true
  try {
    backup(ctx)
    const record = await studioApi('jobs', 'post', { id: ctx[pendingKey].id, ...payload })
    ctx[pendingKey] = null
    if (kind === 'notebook') { ctx.kernel.job = record.id; saveKernel(ctx) }
    if (current !== generation) return
    if (kind === 'evaluation') { latestEvaluation.value = record; snapshot.value = record }
    else applyNotebookResult(record)
    poll(record.id, kind, current)
  } catch (failure) {
    if (current === generation) {
      error.value = failure.message
      if (kind === 'notebook') { running.value = false; runState.value = 'REQUEST_FAILED'; outputs.value = outputs.value.map(cell => cell.status === 'PENDING' ? { ...cell, status: 'IDLE' } : cell) }
    }
  } finally { if (current === generation) submitting.value = false }
}
async function poll (id, kind, current) {
  if (current !== generation) return
  polls.delete(id)
  try {
    const result = await studioApi('jobs', 'get', { id })
    if (current !== generation) return
    if (kind === 'evaluation' && latestEvaluation.value?.id === id) latestEvaluation.value = result
    if (kind === 'notebook') applyNotebookResult(result)
    if (activeStatuses.has(result.status)) { polls.set(id, setTimeout(() => poll(id, kind, current), kind === 'notebook' ? 1000 : 2000)); return }
  } catch (failure) {
    if (current === generation) { error.value = failure.message; polls.set(id, setTimeout(() => poll(id, kind, current), 10000)) }
  }
}
</script>
