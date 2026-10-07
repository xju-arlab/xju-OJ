<template>
  <section class="form-section">
    <h3>AI 评测设置</h3><p>正式比赛开始后，题目、权重与计分方式锁定。赛后可开放练习和公布私榜。</p>
    <el-form-item label="计分方式"><el-select v-model="config.selection"><el-option label="最后一次提交" value="latest" /><el-option label="最高得分" value="best" /></el-select></el-form-item>
    <el-checkbox v-model="config.practice_enabled">赛后允许补题</el-checkbox><el-checkbox v-model="config.private_published">公布私榜（比赛结束后）</el-checkbox>
    <div v-for="(item, index) in config.problems" :key="index" class="ai-contest-setting-row"><span>{{ index + 1 }}</span><el-select v-model="item.id" filterable><el-option v-for="problem in problems" :key="problem.id" :value="problem.id" :label="problem.id + ' · ' + problem.title" /></el-select><el-input-number v-model="item.points" :min="1" :max="10000" /><span>分</span><el-button @click="config.problems.splice(index, 1)">移除</el-button></div>
    <el-button @click="config.problems.push({ id: '', points: 20 })">添加题目</el-button><p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
<script setup>
import { ref, watch } from 'vue'
import { request, studioApi } from '@oj/views/ai/api'
const props = defineProps({ contestId: { type: [String, Number], default: '' } })
const config = ref({ selection: 'latest', practice_enabled: true, private_published: false, problems: [] })
const problems = ref([]); const error = ref('')
let generation = 0
async function load () {
  const current = ++generation
  try {
    const [owned, publicProblems] = await Promise.all([request('admin/ai/problems', 'get', { limit: 100 }), studioApi('problems', 'get', { limit: 100 })])
    if (current !== generation) return
    problems.value = [...new Map([...publicProblems.results, ...owned.results].map(item => [item.id, item])).values()]
    if (props.contestId) { const result = await request('admin/ai/contest', 'get', { contest_id: props.contestId }); if (current === generation) config.value = result }
  } catch (failure) { error.value = failure.message }
}
function validate () { if (!config.value.problems.length || config.value.problems.some(item => !item.id)) throw new Error('请配置 AI 比赛题目') }
async function save (contestId) { validate(); await request('admin/ai/contest', 'put', { contest_id: contestId, ...config.value }) }
watch(() => props.contestId, load, { immediate: true })
defineExpose({ save, validate })
</script>
<style scoped>
.form-section { padding: 20px; border: 1px solid var(--color-border); border-radius: var(--radius-md); }.form-section p { color: var(--color-text-muted); margin: 10px 0 20px; }
.ai-contest-setting-row { display: flex; align-items: center; gap: 12px; margin: 14px 0; }.ai-contest-setting-row .el-select { width: 360px; }
</style>
