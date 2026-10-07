<template>
  <Panel title="AI 题库">
    <div class="ai-admin-tools"><el-button @click="create">新建题目</el-button><el-select v-model="selected" placeholder="选择题目" @change="edit"><el-option v-for="item in problems" :key="item.id" :label="item.id + ' · ' + item.title" :value="item.id" /></el-select></div>
    <p v-if="error" role="alert">{{ error }}</p>
    <el-form v-if="form" label-position="top" class="ai-admin-form" @submit.prevent="save">
      <div class="ai-admin-grid"><el-form-item label="题目编号"><el-input v-model="form.id" :disabled="!!form.version" /></el-form-item><el-form-item label="标题"><el-input v-model="form.title" /></el-form-item><el-form-item label="题型"><el-select v-model="form.type"><el-option v-for="item in categories" :key="item.id" :value="item.id" :label="item.name" /></el-select></el-form-item></div>
      <el-form-item label="任务目标"><el-input v-model="form.objective" type="textarea" :rows="3" /></el-form-item>
      <el-form-item label="实现要求（每行一项）"><el-input v-model="requirements" type="textarea" :rows="3" /></el-form-item>
      <el-form-item label="接口约定"><el-input v-model="form.signature" type="textarea" :rows="2" /></el-form-item>
      <el-form-item label="数据说明"><el-input v-model="form.data" type="textarea" :rows="2" /></el-form-item>
      <el-form-item label="评分说明"><el-input v-model="form.evaluation" type="textarea" :rows="3" /></el-form-item>
      <div class="ai-admin-grid"><el-form-item label="指标名称"><el-input v-model="form.metric" /></el-form-item><el-form-item label="分值"><el-input-number v-model="form.points" :min="1" :max="10000" /></el-form-item><el-form-item label="在公开题库显示"><el-switch v-model="form.visible" /></el-form-item></div>
      <el-form-item v-for="(_, index) in form.cells" :key="index" :label="['准备环境', '作答框架', '公开样例'][index] || '代码单元格'"><CodeMirror v-model="form.cells[index]" mode="text/x-python" /></el-form-item>
      <el-form-item label="公开数据（CSV，总计不超过 1 MiB）"><input type="file" accept=".csv" multiple @change="readFiles" /><div v-for="(_, name) in form.public_files" :key="name">{{ name }} <el-button link @click="delete form.public_files[name]">移除</el-button></div></el-form-item>
      <div class="ai-admin-grid"><el-form-item label="Codabench Phase ID"><el-input-number v-model="form.judge.phase_id" :min="1" /></el-form-item><el-form-item label="公榜评分列"><el-input v-model="form.judge.public_column" /></el-form-item><el-form-item label="达标分数（0–100）"><el-input-number v-model="form.judge.pass_score" :min="0" :max="100" /></el-form-item><el-form-item label="私榜评分列（可选）"><el-input v-model="form.judge.private_column" /></el-form-item><el-form-item label="Accuracy 列（可选，0–1）"><el-input v-model="form.judge.accuracy_column" /></el-form-item><el-form-item label="Notebook 运行秒数"><el-input-number v-model="form.judge.run_seconds" :min="5" :max="600" /></el-form-item></div>
      <el-button type="primary" :loading="saving" @click="save">保存题目</el-button>
    </el-form>
  </Panel>
</template>
<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import CodeMirror from '@/shared/editors/CodeMirrorAdapter.vue'
import { categories } from '@oj/views/ai/studio'
import { request } from '@oj/views/ai/api'

const problems = ref([]); const selected = ref(''); const form = ref(null); const requirements = ref('')
const error = ref(''); const saving = ref(false)
async function load () { try { problems.value = (await request('admin/ai/problems', 'get', { limit: 100 })).results } catch (failure) { error.value = failure.message } }
function create () { selected.value = ''; requirements.value = ''; form.value = { id: '', title: '', type: 'logic', objective: '', signature: '', data: '', evaluation: '', metric: 'Score', points: 100, visible: false, public_files: {}, cells: ['import torch\nfrom torch import nn\nimport numpy as np\nimport pandas as pd', '# 完成你的实现', '# 公开样例'], judge: { phase_id: 1, public_column: 'score', private_column: '', accuracy_column: '', pass_score: 100, run_seconds: 120 } } }
function edit () { form.value = JSON.parse(JSON.stringify(problems.value.find(item => item.id === selected.value))); requirements.value = form.value.requirements.join('\n') }
async function readFiles (event) {
  const files = Array.from(event.target.files || [])
  if (files.some(file => file.size > 1024 * 1024 || !/^[A-Za-z0-9_-]{1,64}\.csv$/.test(file.name))) { error.value = '请上传名称仅含字母、数字、短横线或下划线的 CSV 文件，每个文件最多 1 MiB。'; return }
  const target = form.value
  for (const file of files) { const content = await file.text(); if (form.value === target) target.public_files[file.name] = content }
}
async function save () {
  if (saving.value) return
  saving.value = true; error.value = ''
  try { const result = await request('admin/ai/problems', 'post', { ...form.value, requirements: requirements.value.split('\n').filter(Boolean) }); form.value.version = result.version; selected.value = result.id; await load(); ElMessage.success('题目已保存') }
  catch (failure) { error.value = failure.message }
  finally { saving.value = false }
}
load()
</script>
<style scoped>
.ai-admin-tools { display: flex; gap: 16px; margin-bottom: 24px; }.ai-admin-tools .el-select { width: 320px; }
.ai-admin-form { max-width: 1100px; }.ai-admin-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.ai-admin-form :deep(.el-form-item__content) { display: block; }.ai-admin-form :deep(.cm-editor) { border: 1px solid var(--color-border); }
@media (max-width: 800px) { .ai-admin-grid { grid-template-columns: 1fr; } }
</style>
