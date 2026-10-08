<template>
  <section class="studio-problem-ranking" aria-label="本题排行">
    <p v-if="!authenticated" class="studio-footnote">登录后查看本题排行。</p>
    <template v-else>
      <div class="studio-ranking-toolbar"><span>{{ contestId ? '本场比赛' : '自主练习' }} · {{ board.selection === 'latest' ? '最后一次提交' : '最高分' }} · {{ board.privatePublished ? '私榜' : '公榜' }}</span><button class="studio-text-button" :disabled="loading" @click="load">{{ loading ? '加载中…' : '刷新' }}</button></div>
      <p v-if="error" role="alert" class="studio-error">{{ error }}</p>
      <template v-else>
        <div class="studio-table-wrap"><table class="studio-table"><thead><tr><th>排名</th><th>用户</th><th>得分</th><th>评测状态</th></tr></thead><tbody><tr v-for="row in board.results" :key="row.userId"><td>{{ row.rank }}</td><td><router-link :to="{ name: 'user-home', query: { username: row.username } }">{{ row.username }}</router-link></td><td>{{ row.score == null ? '—' : row.score.toFixed(2) }}</td><td><EvaluationStatus :record="row.record" /></td></tr></tbody></table></div>
        <p v-if="!loading && !board.results.length" class="studio-footnote">暂无评测成绩</p>
        <div v-if="board.total > limit" class="studio-ranking-pagination"><button class="studio-text-button" :disabled="offset === 0 || loading" @click="changePage(-1)">上一页</button><span>{{ offset / limit + 1 }} / {{ Math.ceil(board.total / limit) }}</span><button class="studio-text-button" :disabled="offset + limit >= board.total || loading" @click="changePage(1)">下一页</button></div>
      </template>
    </template>
  </section>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { studioApi } from './api'
import EvaluationStatus from './EvaluationStatus.vue'

const props = defineProps({ problemId: { type: String, required: true }, contestId: { type: String, default: '' }, authenticated: Boolean })
const board = ref({ selection: 'best', privatePublished: false, results: [], total: 0 })
const error = ref(''); const loading = ref(false); const offset = ref(0); const limit = 20
let generation = 0
async function load () {
  const current = ++generation
  if (!props.authenticated) return
  loading.value = true; error.value = ''
  try {
    const result = await studioApi('problem-leaderboard', 'get', { problem_id: props.problemId, contest_id: props.contestId, offset: offset.value, limit })
    if (current === generation) board.value = result
  } catch (failure) { if (current === generation) { error.value = failure.message; board.value.results = [] } }
  finally { if (current === generation) loading.value = false }
}
function changePage (direction) { offset.value += direction * limit; load() }
watch(() => [props.problemId, props.contestId, props.authenticated], () => { offset.value = 0; load() }, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>

<style scoped>
.studio-ranking-toolbar, .studio-ranking-pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; color: var(--color-text-muted); font-size: 12px; }
.studio-ranking-pagination { margin-top: 16px; }
.studio-problem-ranking .studio-table { min-width: 0; }
.studio-problem-ranking .studio-table td, .studio-problem-ranking .studio-table th { padding: 12px 8px; }
.studio-problem-ranking .studio-table td:nth-child(2) { white-space: normal; overflow-wrap: anywhere; }
.studio-problem-ranking .studio-table td:last-child { text-align: right; }
.studio-problem-ranking .studio-footnote { margin-top: 14px; }
</style>
