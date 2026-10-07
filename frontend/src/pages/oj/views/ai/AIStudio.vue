<template>
  <div class="ai-studio">
    <p v-if="error" role="alert" class="studio-error">{{ error }}</p>
    <div v-if="section === 'problems'" class="studio-grid studio-home-grid">
      <section class="studio-main">
        <section class="studio-section">
          <div class="studio-section-title studio-home-title"><h2>AI 比赛</h2><router-link :to="{ name: 'ai-contests' }">查看全部</router-link></div>
          <router-link v-for="contest in allContests.slice(0, 3)" :key="contest.id" class="studio-home-contest" :to="{ name: 'ai-contest', params: { contestID: contest.id } }"><strong>{{ contest.title }}</strong><span class="studio-badge ai-rule">AI</span><ArrowUpRight :size="17" /></router-link>
        </section>
        <div class="studio-section-title studio-home-title"><h2>题库</h2></div>
        <div class="studio-toolbar">
          <div class="studio-filter"><button :class="{ active: !type }" @click="selectType('')">全部</button><button v-for="category in categories" :key="category.id" :class="{ active: type === category.id }" :aria-pressed="type === category.id" @click="selectType(category.id)">{{ category.name }}</button></div>
          <label class="studio-search"><Search :size="16" /><input v-model="keyword" placeholder="搜索题目、知识点" aria-label="搜索 AI 题目" /></label>
        </div>
        <div class="studio-table-wrap">
          <table class="studio-table"><thead><tr><th>题目</th><th>题型</th><th>最近评测</th><th><span class="studio-sr-only">操作</span></th></tr></thead>
            <tbody><tr v-for="problem in filteredProblems" :key="problem.id">
              <td><router-link :to="{ name: 'ai-problem', params: { problemID: problem.id } }" class="studio-problem-title"><span class="studio-mono">{{ problem.id }}</span><strong>{{ problem.title }}</strong></router-link></td>
              <td><span :class="['studio-badge', categoryFor(problem.type).tone]">{{ categoryFor(problem.type).name }}</span></td>
              <td><EvaluationStatus v-if="latestFor(problem.id)" :record="latestFor(problem.id)" /><small v-else>尚未提交</small></td>
              <td><router-link class="studio-open" :to="{ name: 'ai-problem', params: { problemID: problem.id } }" :aria-label="'打开 ' + problem.title"><ArrowUpRight :size="18" /></router-link></td>
            </tr></tbody>
          </table>
          <div v-if="!filteredProblems.length" class="studio-empty"><Search :size="24" /><p>没有找到匹配的题目</p><button class="studio-button" @click="clearFilters">清除筛选</button></div>
        </div>
        <div v-if="problemTotal > 20" class="studio-dialog-actions"><button class="studio-button" :disabled="problemPage === 0" @click="changeProblemPage(-1)">上一页</button><span>{{ problemPage + 1 }}</span><button class="studio-button" :disabled="(problemPage + 1) * 20 >= problemTotal" @click="changeProblemPage(1)">下一页</button></div>
      </section>
      <aside class="studio-sidebar">
        <section class="studio-section"><div class="studio-section-title studio-home-title"><h2>完成评测</h2><span>{{ completed.length }} 道题</span></div><div class="studio-activity-board"><router-link v-for="record in completed" :key="record.problemId" class="studio-activity-row" :title="record.title" :to="{ name: 'ai-problem', params: { problemID: record.problemId }, query: record.contestId ? { contest: record.contestId } : {} }"><EvaluationIcon :status="record.status" /><strong class="studio-activity-title">{{ record.title }}</strong><EvaluationStatus :record="record" inline /></router-link><p v-if="!completed.length" class="studio-empty">完成首次评测后，题目会出现在这里。</p></div></section>
        <section class="studio-section"><div class="studio-section-title studio-home-title"><h2>最近提交</h2><router-link :to="{ name: 'ai-submissions' }">查看全部</router-link></div><div class="studio-activity-board"><router-link v-for="record in activity.slice(0, 5)" :key="record.id" class="studio-activity-row" :data-submission-id="record.id" :title="record.title" :to="{ name: 'ai-problem', params: { problemID: record.problemId }, query: record.contestId ? { contest: record.contestId } : {} }"><EvaluationIcon :status="record.status" /><strong class="studio-activity-title">{{ record.title }}</strong><EvaluationStatus :record="record" inline /></router-link><p v-if="!activity.length" class="studio-empty">暂无提交记录。</p></div></section>
      </aside>
    </div>

    <section v-else-if="section === 'contests'">
      <div class="studio-section-title studio-home-title"><h2>AI 比赛</h2><router-link :to="{ name: 'ai-studio' }">返回 AI 工作台</router-link></div>
      <div class="studio-toolbar"><div class="studio-rule-switch" aria-label="比赛赛制"><router-link to="/contest?rule_type=ACM">ACM</router-link><router-link to="/contest?rule_type=OI">OI</router-link><span class="active">AI</span><small>{{ $t('m.AI_Evaluation') }}</small></div><a v-if="isAdmin" class="studio-button" href="/admin/contest/create">创建比赛</a></div>
      <p class="studio-description">以测试点、模型表现和隐藏集指标评测，支持限时考核与持续挑战。</p>
      <router-link v-for="contest in allContests" :key="contest.id" :to="{ name: 'ai-contest', params: { contestID: contest.id } }" class="studio-contest-row">
        <span class="studio-contest-icon"><Trophy :size="23" /></span><div><div class="studio-inline"><span class="studio-badge ai-rule">AI</span><small>{{ statusName(contest.status) }}</small></div><h2>{{ contest.title }}</h2><p>{{ formatDate(contest.start_time) }}（北京时间）</p></div><ArrowUpRight :size="21" />
      </router-link>
      <div v-if="contestTotal > 20" class="studio-dialog-actions"><button class="studio-button" :disabled="contestPage === 0" @click="changeContestPage(-1)">上一页</button><span>{{ contestPage + 1 }}</span><button class="studio-button" :disabled="(contestPage + 1) * 20 >= contestTotal" @click="changeContestPage(1)">下一页</button></div>
    </section>

    <section v-else>
      <div class="studio-section-title"><h2>提交记录</h2><router-link :to="{ name: 'ai-studio' }">返回 AI 工作台</router-link></div>
      <div v-if="!records.length" class="studio-empty"><History :size="28" /><h3>还没有提交记录</h3><p>提交评测后，可以在这里查看状态与答卷。</p><router-link class="studio-button" :to="{ name: 'ai-studio' }">浏览题目 <ArrowRight :size="15" /></router-link></div>
      <div v-else class="studio-table-wrap"><table class="studio-table"><thead><tr><th>题目</th><th>时间（北京时间）</th><th>范围</th><th>状态 / 分数</th><th>答卷</th></tr></thead><tbody><tr v-for="record in records" :key="record.id"><td>{{ record.problemId }} · {{ record.title }}</td><td>{{ formatDate(record.createdAt) }}</td><td>{{ record.official ? '正式比赛' : '自主练习' }}</td><td><EvaluationStatus :record="record" /></td><td><button class="studio-text-button" @click="exportRecord(record)">下载 Notebook</button></td></tr></tbody></table></div>
    </section>

    <div v-if="section === 'submissions' && recordTotal > 20" class="studio-dialog-actions"><button class="studio-button" :disabled="recordPage === 0" @click="changePage(-1)">上一页</button><span>{{ recordPage + 1 }}</span><button class="studio-button" :disabled="(recordPage + 1) * 20 >= recordTotal" @click="changePage(1)">下一页</button></div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, ArrowUpRight, History, Search, Trophy } from 'lucide-vue-next'
import store from '@/store'
import { categories, categoryFor, download, formatDate, notebookFor } from './studio'
import { request, studioApi } from './api'
import EvaluationStatus from './EvaluationStatus.vue'
import EvaluationIcon from './EvaluationIcon.vue'
import './studio.less'

const props = defineProps({ section: { type: String, default: 'problems' } })
const route = useRoute(); const router = useRouter()
const keyword = ref(''); const type = ref(''); const error = ref('')
const problems = ref([]); const records = ref([]); const allContests = ref([]); const completed = ref([])
const recordPage = ref(0); const recordTotal = ref(0)
const problemPage = ref(0); const problemTotal = ref(0); const contestPage = ref(0); const contestTotal = ref(0)
const authenticated = computed(() => store.getters.isAuthenticated)
const isAdmin = computed(() => store.getters.isAdminRole)
const activity = computed(() => records.value)
const latestFor = id => problems.value.find(problem => problem.id === id)?.latest
const filteredProblems = computed(() => problems.value)
function selectType (value) { type.value = value; router.replace({ query: value ? { type: value } : {} }) }
function clearFilters () { keyword.value = ''; selectType('') }
const statusName = status => ({ '0': '进行中', '1': '未开始', '-1': '已结束' })[String(status)] || ''
let generation = 0; let timer
async function load () {
  const current = ++generation
  clearTimeout(timer)
  error.value = ''
  type.value = categories.some(item => item.id === route.query.type) ? route.query.type : ''
  try {
    const results = await Promise.all([
      studioApi('problems', 'get', { limit: 20, offset: problemPage.value * 20, type: type.value, keyword: keyword.value.trim() }),
      request('contests', 'get', { rule_type: 'AI', limit: 20, offset: contestPage.value * 20 }),
      authenticated.value ? studioApi('jobs', 'get', { limit: 20, offset: recordPage.value * 20 }) : Promise.resolve({ results: [], total: 0 }),
      authenticated.value ? studioApi('completed') : Promise.resolve([])
    ])
    if (current !== generation) return
    problems.value = results[0].results; allContests.value = results[1].results
    problemTotal.value = results[0].total; contestTotal.value = results[1].total
    records.value = results[2].results; recordTotal.value = results[2].total; completed.value = results[3]
  } catch (failure) { if (current === generation) error.value = failure.message }
  finally { if (current === generation) timer = setTimeout(load, 10000) }
}
function changePage (delta) { recordPage.value += delta; load() }
function changeProblemPage (delta) { problemPage.value += delta; load() }
function changeContestPage (delta) { contestPage.value += delta; load() }
async function exportRecord (record) {
  try {
    const detail = await studioApi('jobs', 'get', { id: record.id })
    download(record.problemId + '-submission.ipynb', JSON.stringify(notebookFor({ title: record.title, objective: '' }, detail.payload.cells), null, 2))
  } catch (failure) { error.value = failure.message }
}
let searchTimer
watch(keyword, () => { clearTimeout(searchTimer); problemPage.value = 0; searchTimer = setTimeout(load, 300) })
watch(() => [route.fullPath, authenticated.value, props.section, store.getters.user.id], () => { recordPage.value = 0; problemPage.value = 0; contestPage.value = 0; load() }, { immediate: true })
onBeforeUnmount(() => { generation++; clearTimeout(timer); clearTimeout(searchTimer) })
</script>
