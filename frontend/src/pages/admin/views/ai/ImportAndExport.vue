<template>
  <div class="ai-package-manager">
    <Panel title="导入 AI 题目">
      <template #header><el-button link @click="help = true">题包格式</el-button></template>
      <p class="package-hint">支持单题 ZIP、由多个单题 ZIP 组成的批量 ZIP。每批最多 20 道，16 MiB。</p>
      <div class="package-actions">
        <label class="package-picker"><input ref="fileInput" type="file" accept=".zip,application/zip" :disabled="uploading" @change="choose" /><span>选择题包</span></label>
        <span class="package-filename">{{ file?.name || '未选择文件' }}</span>
        <el-button type="primary" :disabled="!file" :loading="uploading" @click="preview">上传并校验</el-button>
      </div>
      <p v-if="error" class="package-error" role="alert">{{ error }}</p>
      <section v-if="current" class="package-preview" aria-label="题包预览">
        <div class="package-heading"><strong>{{ current.filename }}</strong><el-tag :type="statusType(current.status)">{{ statusName(current.status) }}</el-tag></div>
        <el-table :data="current.problems">
          <el-table-column prop="title" label="标题" min-width="200" />
          <el-table-column label="题型" width="130"><template #default="{ row }">{{ categoryFor(row.type).name }}</template></el-table-column>
          <el-table-column prop="metric" label="指标" width="110" />
          <el-table-column prop="cells" label="代码单元格" width="110" />
          <el-table-column label="公开数据" min-width="160"><template #default="{ row }">{{ row.files.join('、') || '—' }}</template></el-table-column>
        </el-table>
        <p class="package-hint">{{ active(current) ? '正在注册评测环境，完成后将整批创建题目。离开页面不影响导入。' : current.status === 'SUCCEEDED' ? '导入完成' : '题号由系统自动分配，已有题目不会被覆盖。' }}</p>
        <p v-if="current.message" class="package-error" role="alert">{{ current.message }}</p>
        <div v-if="['PREVIEW', 'FAILED'].includes(current.status)" class="package-actions">
          <el-checkbox v-model="publish">导入后公开</el-checkbox>
          <el-button type="primary" :loading="confirming" @click="confirm">{{ current.status === 'FAILED' ? '重试导入' : '确认导入' }}</el-button>
          <el-button v-if="current.status === 'PREVIEW'" :disabled="confirming" @click="discard(current)">删除预览</el-button>
        </div>
        <div v-if="current.result.length" class="package-result"><router-link v-for="item in current.result" :key="item.id" :to="{ path: '/ai/problems', query: { id: item.id } }">{{ item.id }} · {{ item.title }}</router-link></div>
      </section>
      <el-collapse v-if="history.length" class="package-history"><el-collapse-item title="导入记录" name="history">
        <el-table :data="history">
          <el-table-column prop="filename" label="题包" min-width="180" />
          <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusName(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="时间" min-width="160"><template #default="{ row }">{{ $filters.localtime(row.createdAt) }}</template></el-table-column>
          <el-table-column width="100"><template #default="{ row }"><el-button link @click="select(row)">查看</el-button></template></el-table-column>
        </el-table>
      </el-collapse-item></el-collapse>
    </Panel>
    <Panel title="导出 AI 题目">
      <template #header><div class="package-search"><el-input v-model="keyword" placeholder="搜索题号或标题" clearable @keyup.enter="search" @clear="search" /><el-button @click="search">搜索</el-button></div></template>
      <el-table :data="problems" v-loading="loading" row-key="id" @selection-change="selected = $event">
        <el-table-column type="selection" width="50" :selectable="row => row.packaged" />
        <el-table-column prop="id" label="题号" width="110" />
        <el-table-column label="标题" min-width="200"><template #default="{ row }"><router-link :to="{ path: '/ai/problems', query: { id: row.id } }">{{ row.title }}</router-link></template></el-table-column>
        <el-table-column label="题型" width="130"><template #default="{ row }">{{ categoryFor(row.type).name }}</template></el-table-column>
        <el-table-column label="可见性" width="100"><template #default="{ row }">{{ row.visible ? '公开' : '隐藏' }}</template></el-table-column>
        <el-table-column label="题包" width="120"><template #default="{ row }">{{ row.packaged ? '完整' : '待归档' }}</template></el-table-column>
      </el-table>
      <div class="package-actions package-footer">
        <el-button type="primary" :disabled="!selected.length || selected.length > 20" :loading="exporting" @click="exportSelected">导出所选{{ selected.length ? `（${selected.length}）` : '' }}</el-button>
        <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="loadProblems" />
      </div>
      <p class="package-hint">导出包含私有评测程序与参考数据，仅用于出题管理和迁移。</p>
    </Panel>
    <LegacyDialog :visible="help" @update:visible="help = $event" title="AI 题包格式" width="640px">
      <p>每个单题 ZIP 的根目录：</p>
      <pre class="package-layout">problem.json                 题面、题型与评分配置
starter.ipynb                作答框架（Notebook v4）
data/*.csv                   公开数据，可选
evaluation/scoring/program.py    评分程序
evaluation/reference/            私有参考数据
evaluation/ingestion/program.py  代码运行程序
evaluation/input/                评测输入，可选</pre>
      <p>三种题型：logic（逻辑实现）、model（模型定义）、challenge（数据挑战）。数据挑战直接对 predictions.csv 评分，不包含 ingestion 和 input。</p>
      <p>problem.json 使用 <code>format: "xju-ai-problem"</code>、<code>version: 1</code>；不填写服务器 Phase ID。Notebook 只导入代码，输出与执行记录自动清除。</p>
      <a href="https://github.com/xju-arlab/xju-OJ/blob/main/docs/operations/ai-problem-packages.md" target="_blank" rel="noopener noreferrer">完整格式与出题工具说明</a>
    </LegacyDialog>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { request } from '@oj/views/ai/api'
import { categoryFor } from '@oj/views/ai/studio'
import utils from '@/utils/utils'

const file = ref(null); const fileInput = ref(null); const uploading = ref(false); const confirming = ref(false)
const current = ref(null); const publish = ref(false); const error = ref(''); const history = ref([]); const help = ref(false)
const problems = ref([]); const selected = ref([]); const keyword = ref(''); const page = ref(1); const total = ref(0)
const loading = ref(false); const exporting = ref(false)
let stopped = false; let timer; let generation = 0; let historyGeneration = 0
const active = item => ['PENDING', 'RUNNING'].includes(item.status)
const statusName = value => ({ PREVIEW: '待确认', PENDING: '等待导入', RUNNING: '正在导入', SUCCEEDED: '导入成功', FAILED: '导入失败' }[value] || value)
const statusType = value => value === 'SUCCEEDED' ? 'success' : value === 'FAILED' ? 'danger' : active({ status: value }) ? 'warning' : 'info'
function choose (event) { file.value = event.target.files?.[0] || null; error.value = '' }
function select (item) { historyGeneration++; current.value = item; publish.value = item.publish }
async function preview () {
  if (uploading.value || !file.value) return
  if (!/\.zip$/i.test(file.value.name) || file.value.size > 16 * 1024 * 1024) { error.value = '请选择不超过 16 MiB 的 ZIP 题包'; return }
  uploading.value = true; error.value = ''
  const body = new FormData(); body.append('file', file.value)
  try {
    select(await request('admin/ai/packages', 'post', body))
    file.value = null; if (fileInput.value) fileInput.value.value = ''
    await loadHistory()
  } catch (failure) { error.value = failure.message } finally { uploading.value = false }
}
async function confirm () {
  if (confirming.value || !current.value) return
  confirming.value = true; error.value = ''
  try { select(await request('admin/ai/packages/confirm', 'post', { id: current.value.id, publish: publish.value })); await loadHistory() }
  catch (failure) { error.value = failure.message } finally { confirming.value = false }
}
async function discard (item) {
  try {
    await request('admin/ai/packages?id=' + encodeURIComponent(item.id), 'delete')
    if (current.value?.id === item.id) current.value = null
    await loadHistory()
  } catch (failure) { error.value = failure.message }
}
async function loadHistory () {
  const requestId = ++historyGeneration
  const rows = await request('admin/ai/packages')
  if (stopped || requestId !== historyGeneration) return
  const previous = current.value
  history.value = rows
  if (previous) {
    const item = rows.find(row => row.id === previous.id) || await request('admin/ai/packages', 'get', { id: previous.id })
    if (stopped || requestId !== historyGeneration) return
    if (item) {
      current.value = item
      if (active(previous) && item.status === 'SUCCEEDED') { await loadProblems(); ElMessage.success('题目导入成功') }
    }
  } else if (rows.some(active)) select(rows.find(active))
}
async function poll () {
  try { await loadHistory() } catch (failure) { if (!stopped) error.value = failure.message }
  finally { if (!stopped) timer = setTimeout(poll, 3000) }
}
async function loadProblems () {
  const requestId = ++generation; loading.value = true
  try {
    const result = await request('admin/ai/problems', 'get', { keyword: keyword.value, offset: (page.value - 1) * 20, limit: 20 })
    if (stopped || requestId !== generation) return
    problems.value = result.results; total.value = result.total; selected.value = []
  } catch (failure) { if (requestId === generation) error.value = failure.message }
  finally { if (requestId === generation) loading.value = false }
}
function search () { page.value = 1; loadProblems() }
async function exportSelected () {
  exporting.value = true
  try { await utils.downloadFile('/admin/ai/packages/export?' + selected.value.map(row => 'problem_id=' + encodeURIComponent(row.id)).join('&')) }
  catch (failure) { error.value = failure.message } finally { exporting.value = false }
}
onBeforeUnmount(() => { stopped = true; generation++; historyGeneration++; clearTimeout(timer) })
loadProblems(); poll()
</script>

<style scoped>
.package-hint { margin: 12px 0; color: var(--color-text-muted); line-height: 1.7; }
.package-actions, .package-heading, .package-search { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.package-heading { justify-content: space-between; margin-bottom: 16px; }
.package-picker { position: relative; overflow: hidden; padding: 8px 14px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); cursor: pointer; }
.package-picker input { position: absolute; inset: 0; width: 100%; opacity: 0; cursor: pointer; }
.package-picker:focus-within { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.package-filename { overflow-wrap: anywhere; }.package-error { color: var(--el-color-danger); margin: 12px 0; }
.package-preview { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--color-border); }
.package-result { display: grid; gap: 8px; margin-top: 12px; }.package-history { margin-top: 24px; }
.package-footer { justify-content: space-between; margin-top: 20px; }.package-search .el-input { width: 220px; }
.package-layout { overflow-x: auto; padding: 16px; background: var(--color-bg-subtle); line-height: 1.8; }
</style>
