<template>
  <div class="contest-detail-page ai-contest-page">
    <p v-if="error" role="alert" class="ai-contest-note">{{ error }}</p>
    <section v-if="!contest" class="contest-overview ai-contest-empty">
      <h2>比赛暂不可用</h2>
      <router-link class="ai-preview-link" :to="{ name: 'ai-contests' }">返回列表</router-link>
    </section>

    <template v-else>
      <ContestAnnouncementBanner v-if="!contest.accessError" :contest-id="contest.id" />
      <section class="contest-hero" aria-labelledby="ai-contest-title">
        <div class="contest-breadcrumb">
          <router-link :to="{ name: 'contest-list', query: { rule_type: 'AI' } }">{{ $t('m.Contests') }}</router-link>
          <span aria-hidden="true">/</span><span>{{ contest.id }}</span>
        </div>
        <div class="contest-hero-main">
          <div class="contest-heading">
            <span class="contest-mark" aria-hidden="true"><Icon type="trophy" /></span>
            <div class="contest-title-line">
              <h1 id="ai-contest-title">{{ contest.title }}</h1>
              <div class="contest-title-badges">
                <span class="contest-rule rule-ai">AI</span>
                <span :class="['contest-status', statusClass]">{{ statusLabel }}</span>
              </div>
            </div>
          </div>
        </div>
        <dl class="contest-meta">
          <div><dt><CalendarDays aria-hidden="true" />开始时间</dt><dd>{{ formatDate(contest.start_time) }} <small>北京时间</small></dd></div>
          <div><dt><Clock3 aria-hidden="true" />比赛时长</dt><dd>{{ Math.round((Date.parse(contest.end_time) - Date.parse(contest.start_time)) / 60000) }} 分钟</dd></div>
          <div><dt><MapPin aria-hidden="true" />创建者</dt><dd>{{ contest.created_by?.username }}</dd></div>
          <div><dt><Award aria-hidden="true" />总分</dt><dd>{{ totalPoints }} 分</dd></div>
        </dl>
      </section>

      <nav class="contest-tabs" aria-label="AI 比赛内容">
        <button v-for="item in tabs" :key="item.id" type="button"
                :class="['contest-tab', { 'is-active': tab === item.id }]"
                :aria-pressed="tab === item.id" @click="tab = item.id">
          <Icon :type="item.icon" /><span>{{ item.name }}</span>
        </button>
      </nav>

      <main :class="['contest-content', { 'is-root': tab === 'overview' }]">
        <div v-if="tab === 'overview'" class="contest-overview-grid">
          <section class="contest-overview" aria-labelledby="ai-contest-overview-title">
            <div class="section-heading">
              <span class="section-icon" aria-hidden="true"><Icon type="file-text" /></span>
              <div><p>{{ $t('m.Contests') }}</p><h2 id="ai-contest-overview-title">{{ $t('m.Overview') }}</h2></div>
            </div>
            <div class="contest-description ai-contest-description">
              <div class="markdown-body" v-html="description"></div>
              <h3>考核题目</h3>
              <router-link v-for="(problem, index) in contestProblems" :key="problem.id"
                           class="ai-contest-problem" :to="problemRoute(problem.id)">
                <span class="ai-contest-problem-number">{{ String(index + 1).padStart(2, '0') }}</span>
                <div><strong>{{ problem.title }}</strong></div>
                <span class="ai-contest-points">{{ problem.points }} 分</span><ChevronRight :size="14" aria-hidden="true" />
              </router-link>
            </div>
          </section>

          <aside class="contest-guide" aria-labelledby="ai-contest-guide-title">
            <div class="section-heading compact">
              <span class="section-icon" aria-hidden="true"><Icon type="info-circle" /></span>
              <div><p>XJU-OJ</p><h2 id="ai-contest-guide-title">比赛规则</h2></div>
            </div>
            <dl>
              <div><dt>赛制</dt><dd class="contest-rule rule-ai">AI</dd></div>
              <div><dt>说明</dt><dd>{{ $t('m.AI_Evaluation') }}</dd></div>
              <div><dt>计分</dt><dd>{{ contest.scorePolicy === 'best' ? '最高得分' : '最后一次提交' }}</dd></div>
              <div><dt>作答方式</dt><dd>Notebook</dd></div>
              <div><dt>赛后练习</dt><dd>与正式成绩分开</dd></div>
            </dl>
            <button type="button" class="contest-primary-link" @click="tab = 'problems'">
              <span>{{ $t('m.Problems_List') }}</span><Icon type="arrow-down-b" />
            </button>
            <router-link v-if="contestProblems.length" class="ai-preview-link" :to="problemRoute(contestProblems[0].id)">
              进入作答<ChevronRight :size="14" aria-hidden="true" />
            </router-link>
            <form v-if="contest.status !== '-1' && !contest.registered" class="ai-registration" @submit.prevent="register"><label v-if="contest.contest_type !== 'Public'">比赛密码<input v-model="password" type="password" autocomplete="off" /></label><button class="contest-primary-link" :disabled="registering">{{ registering ? '报名中…' : '报名参赛' }}</button></form>
            <p v-if="contest.accessError" class="ai-contest-note">{{ contest.accessError }}</p>
            <p class="ai-contest-note">保存草稿与正式交卷分开，正式评测以收到的答卷快照为准。</p>
          </aside>
        </div>

        <section v-else-if="tab === 'problems'" class="contest-problem-panel" aria-labelledby="ai-contest-problems-title">
          <header class="problem-panel-header">
            <div><p>{{ $t('m.Problems') }}</p><h2 id="ai-contest-problems-title">{{ $t('m.Problems_List') }}</h2></div>
            <span class="problem-count">{{ contestProblems.length }}</span>
          </header>
          <div v-if="contestProblems.length" class="problem-table-wrap">
            <table class="contest-problem-table">
              <thead><tr><th class="problem-id">#</th><th>{{ $t('m.Title') }}</th><th>类型</th><th class="numeric">分值</th><th class="problem-status">最近评测</th></tr></thead>
              <tbody>
                <tr v-for="problem in contestProblems" :key="problem.id" tabindex="0"
                    @click="router.push(problemRoute(problem.id))" @keydown.enter.prevent="router.push(problemRoute(problem.id))">
                  <td class="problem-id"><span>{{ problem.id }}</span></td>
                  <td><router-link class="problem-title-link" :to="problemRoute(problem.id)" @click.stop>
                    <strong>{{ problem.title }}</strong><Icon type="arrow-down-b" />
                  </router-link></td>
                  <td><span :class="['ai-problem-type', categoryFor(problem.type).tone]">{{ categoryFor(problem.type).name }}</span></td>
                  <td class="numeric">{{ problem.points }}</td>
                  <td class="problem-status"><EvaluationStatus v-if="latestFor(problem.id)" :record="latestFor(problem.id)" inline /><span v-else class="attempt-status is-empty">尚未提交</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="problem-empty"><Icon type="ios-photos" /><p>{{ contest.accessError || $t('m.No_Problems') }}</p></div>
        </section>

        <section v-else class="contest-problem-panel" aria-labelledby="ai-contest-scores-title">
          <header class="problem-panel-header"><div><p>AI</p><h2 id="ai-contest-scores-title">成绩</h2></div></header>
          <div v-if="!scores.length" class="ai-contest-empty">
            <BarChart3 :size="30" aria-hidden="true" /><h3>暂无正式成绩</h3>
            <p>{{ scoreError || '正式比赛提交评测完成后，将在这里显示成绩。' }}</p>
            <router-link class="ai-preview-link" :to="{ name: 'ai-submissions' }">查看我的提交<ChevronRight :size="14" aria-hidden="true" /></router-link>
          </div>
          <div v-else class="problem-table-wrap"><table class="contest-problem-table"><thead><tr><th>排名</th><th>选手</th><th v-for="item in contestProblems" :key="item.id">{{ item.id }}</th><th>总分</th></tr></thead><tbody><tr v-for="row in scores" :key="row.userId"><td>{{ row.rank }}</td><td>{{ row.username }}</td><td v-for="item in contestProblems" :key="item.id">{{ row.scores[item.id]?.score ?? '—' }}</td><td>{{ row.total }}</td></tr></tbody></table><p class="ai-contest-note">{{ contest.privatePublished ? '私榜已公布' : '当前为公榜成绩' }} · {{ contest.scorePolicy === 'best' ? '最高得分' : '最后一次提交' }}</p></div>
        </section>
      </main>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DOMPurify from 'dompurify'
import { Award, BarChart3, CalendarDays, ChevronRight, Clock3, MapPin } from 'lucide-vue-next'
import store from '@/store'
import { categoryFor, formatDate } from './studio'
import { studioApi, request } from './api'
import EvaluationStatus from './EvaluationStatus.vue'
import ContestAnnouncementBanner from '@oj/components/ContestAnnouncementBanner.vue'

const route = useRoute(); const router = useRouter()
const contest = ref(null); const activity = ref([]); const scores = ref([])
const error = ref(''); const scoreError = ref(''); const password = ref(''); const registering = ref(false)
const authenticated = computed(() => store.getters.isAuthenticated)
const contestProblems = computed(() => contest.value?.problems || [])
const totalPoints = computed(() => contest.value?.totalPoints || 0)
const description = computed(() => DOMPurify.sanitize(contest.value?.description || ''))
const statusLabel = computed(() => ({ '0': '进行中', '1': '未开始', '-1': '已结束' })[contest.value?.status] || '')
const statusClass = computed(() => ({ '0': 'status-underway', '1': 'status-not-started', '-1': 'status-ended' })[contest.value?.status] || '')
const latestFor = id => activity.value.find(record => record.problemId === id)
const tab = ref('overview')
const tabs = [{ id: 'overview', name: '概览', icon: 'home' }, { id: 'problems', name: '题目', icon: 'ios-photos' }, { id: 'scores', name: '成绩', icon: 'stats-bars' }]
const problemRoute = id => ({ name: 'ai-problem', params: { problemID: id }, query: { contest: contest.value.id } })
let timer; let generation = 0
async function load () {
  const current = ++generation
  clearTimeout(timer)
  const scope = { contest_id: route.params.contestID }
  try {
    const detail = await studioApi('contest', 'get', scope)
    if (current !== generation) return
    contest.value = detail; error.value = ''
    if (authenticated.value) {
      const submissions = await studioApi('jobs', 'get', { ...scope, latest_per_problem: 1, limit: 100 })
      if (current !== generation) return
      activity.value = submissions.results
    } else activity.value = []
    if (detail.accessError) { scores.value = []; scoreError.value = detail.accessError }
    if (tab.value === 'scores' && !detail.accessError) {
      try {
        const board = await studioApi('leaderboard', 'get', scope)
        if (current === generation) { scores.value = board.results; scoreError.value = '' }
      } catch (failure) { if (current === generation) { scoreError.value = failure.message; scores.value = [] } }
    }
  } catch (failure) { if (current === generation) error.value = failure.message }
  finally { if (current === generation) timer = setTimeout(load, 10000) }
}
async function register () {
  if (registering.value) return
  registering.value = true
  try { await request('contest/register', 'post', { contest_id: contest.value.id, password: password.value }); password.value = ''; await load() }
  catch (failure) { error.value = failure.message }
  finally { registering.value = false }
}
watch(() => [route.params.contestID, authenticated.value], () => { contest.value = null; scores.value = []; tab.value = 'overview'; load() }, { immediate: true })
watch(tab, load)
onBeforeUnmount(() => { generation++; clearTimeout(timer) })
</script>

<style scoped lang="less">
@import "@/styles/contest-detail.less";
@import "@/styles/contest-problems.less";

.ai-contest-page { font-size: 14px; }
.ai-registration input { width: 100%; padding: 8px; margin: 8px 0; border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
.ai-contest-page * { box-sizing: border-box; }
.ai-contest-page a { text-decoration: none; }
.contest-breadcrumb { overflow-wrap: anywhere; }
.contest-mark { border-color: var(--color-border); background: var(--color-bg); color: var(--color-link); }
.rule-ai { color: var(--color-link); background: transparent; }
.contest-meta small { margin-left: 5px; color: var(--color-text-faint); font-size: 10px; font-weight: 400; }
.ai-contest-description { font-size: 13px; line-height: 1.9; }
.ai-contest-description p { margin: 0; color: var(--color-text-muted); }
.ai-contest-description h3 { margin: 24px 0 10px; font-size: 15px; font-weight: 650; }
.ai-contest-problem { display: flex; align-items: center; gap: 14px; padding: 15px 0; border-bottom: 1px solid var(--color-border); color: var(--color-text); }
.ai-contest-problem:last-child { border-bottom: 0; padding-bottom: 0; }
.ai-contest-problem > div { flex: 1; min-width: 0; }
.ai-contest-problem strong { font-weight: 600; }
.ai-contest-problem small { display: block; color: var(--color-text-muted); font-size: 12px; }
.ai-contest-problem:hover strong { color: var(--color-link); }
.ai-contest-problem-number { color: var(--color-text-faint); font: 12px var(--font-mono); }
.ai-contest-points { flex: none; color: var(--color-text-muted); font-size: 12px; }
.ai-contest-problem > svg { flex: none; color: var(--color-text-faint); }
.ai-preview-link { display: inline-flex; align-items: center; justify-content: center; gap: 6px; margin-top: 16px; color: var(--color-link); font-size: 12px; }
.contest-guide > .ai-preview-link { display: flex; }
.ai-contest-note { margin: 14px 0 0; color: var(--color-text-faint); font-size: 11px; line-height: 1.8; }
.problem-table-wrap { position: relative; }
.contest-problem-table { min-width: 760px; }
.contest-problem-table .problem-status { width: auto; white-space: nowrap; }
.contest-problem-table .evaluation-status { justify-content: flex-end; }
.ai-problem-type { display: inline-flex; padding: 3px 6px; border-radius: 3px; font-size: 11px; line-height: 1.5; white-space: nowrap; }
.ai-problem-type.orange { background: var(--tag-course-bg); color: var(--cat-course); }
.ai-problem-type.purple { background: var(--tag-recommend-bg); color: var(--cat-recommend); }
.ai-problem-type.teal { background: var(--tag-tools-bg); color: var(--cat-tools); }
.ai-contest-empty { padding: 55px 20px; text-align: center; color: var(--color-text-muted); }
.ai-contest-empty > svg { color: var(--color-text-faint); }
.ai-contest-empty h2, .ai-contest-empty h3 { margin: 14px 0; color: var(--color-text); }
.ai-contest-empty p { margin: 0; font-size: 13px; line-height: 1.8; }
@media (max-width: 620px) {
  .contest-title-line { flex: 1; }
  .ai-contest-problem { gap: 10px; }
  .ai-contest-problem small { font-size: 11px; }
}
</style>
