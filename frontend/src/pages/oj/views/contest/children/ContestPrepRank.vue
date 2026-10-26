<template>
  <section class="prep-rank" :aria-label="$t('m.Rankings')">
    <header class="prep-rank-header">
      <button type="button" class="prep-rank-refresh" :disabled="loading" :aria-label="$t('m.Refresh')" @click="load">
        <Icon type="refresh" />
      </button>
    </header>
    <div class="prep-rank-scroll">
      <table class="prep-rank-table">
        <thead>
          <tr>
            <th class="rank-column">#</th>
            <th class="user-column">{{ $t('m.Username') }}</th>
            <th class="score-column">{{ isOI ? $t('m.Total_Score') : $t('m.Rank_Solved_Problems') }}</th>
            <th v-if="!isOI" class="score-column">{{ $t('m.Prep_Penalty') }}</th>
            <th v-for="problem in problems" :key="problem.id" class="problem-column" :title="problem.title">{{ problem._id }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="row.user.id" :class="{ 'is-me': row.user.id === currentUserId }">
            <td class="rank-column">{{ index + 1 }}</td>
            <td class="user-column">
              <span class="user-name">{{ row.user.username }}</span>
              <span v-if="row.authored.length" class="role-chip is-author" :title="$t('m.Prep_Author')">
                {{ $t('m.Prep_Rank_Authored', { labels: row.authored.join(', ') }) }}
              </span>
              <span v-else-if="row.role" :class="['role-chip', `is-${row.role.toLowerCase()}`]">{{ $t(`m.Prep_Role_${row.role}`) }}</span>
            </td>
            <td class="score-column"><strong>{{ isOI ? row.total_score : `${row.accepted_number} / ${problems.length}` }}</strong></td>
            <td v-if="!isOI" class="score-column">{{ formatPenalty(row.total_time) }}</td>
            <td v-for="problem in problems" :key="problem.id" :class="['problem-column', cellClass(row, problem)]">
              <template v-if="isOI">{{ cell(row, problem) === undefined ? '' : cell(row, problem) }}</template>
              <template v-else-if="cell(row, problem)">
                <span v-if="cell(row, problem).is_ac" class="cell-time">{{ formatTime(cell(row, problem).ac_time) }}</span>
                <span v-if="cell(row, problem).error_number" class="cell-tries">-{{ cell(row, problem).error_number }}</span>
              </template>
            </td>
          </tr>
          <tr v-if="!loading && !rows.length">
            <td :colspan="problems.length + (isOI ? 3 : 4)" class="prep-rank-empty">{{ $t('m.No_Submissions') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script>
import api from '@oj/api'
import { mapGetters } from '@/store/compat'

export default {
  name: 'ContestPrepRank',
  data () {
    return {
      loading: false,
      problems: [],
      rows: [],
      ruleType: 'ACM',
      timer: null,
      generation: 0
    }
  },
  computed: {
    ...mapGetters(['user']),
    contestID () {
      return this.$route.params.contestID
    },
    currentUserId () {
      return this.user && this.user.id
    },
    isOI () {
      return this.ruleType === 'OI'
    }
  },
  mounted () {
    this.load()
    this.timer = setInterval(() => { if (!document.hidden) this.load() }, 15000)
  },
  beforeUnmount () {
    clearInterval(this.timer)
  },
  methods: {
    async load () {
      const generation = ++this.generation
      this.loading = true
      try {
        const res = await api.getPrepRank(this.contestID)
        if (generation !== this.generation) return
        const data = res.data.data
        this.ruleType = data.rule_type
        this.problems = data.problems
        this.rows = data.results
      } catch (_) {
        // The API client already shows the error.
      } finally {
        if (generation === this.generation) this.loading = false
      }
    },
    cell (row, problem) {
      return row.submission_info[String(problem.id)]
    },
    cellClass (row, problem) {
      const info = this.cell(row, problem)
      if (info === undefined || info === null) return ''
      if (this.isOI) return info >= problem.total_score && problem.total_score > 0 ? 'is-ac' : 'is-partial'
      if (info.is_first_ac) return 'is-first-ac'
      if (info.is_ac) return 'is-ac'
      return info.error_number ? 'is-wa' : ''
    },
    formatTime (seconds) {
      const total = Math.floor(seconds)
      const hours = Math.floor(total / 3600)
      const minutes = String(Math.floor(total % 3600 / 60)).padStart(2, '0')
      const secs = String(total % 60).padStart(2, '0')
      return `${hours}:${minutes}:${secs}`
    },
    formatPenalty (seconds) {
      return Math.floor(seconds / 60)
    }
  }
}
</script>

<style scoped lang="less">
.prep-rank {
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg);
}
.prep-rank-header {
  display: flex;
  min-height: 52px;
  align-items: center;
  justify-content: flex-end;
  padding: 0 16px;
  border-bottom: 1px solid var(--color-border);
}
.prep-rank-refresh {
  display: inline-flex;
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
  color: var(--color-text-muted);
  cursor: pointer;
  :deep(.legacy-icon) { display: inline-flex; }
  &:disabled { opacity: .5; cursor: wait; }
}
.prep-rank-scroll { overflow-x: auto; }
.prep-rank-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  th, td { height: 44px; padding: 0 10px; border-bottom: 1px solid var(--color-border); text-align: center; white-space: nowrap; }
  th { background: #fcfbf9; color: var(--color-text-muted); font-size: 12px; font-weight: 600; }
  // Highlight rows without hiding the result colours of the problem cells.
  tbody tr:hover td:not(.problem-column) { background: var(--color-bg-subtle); }
  tr.is-me td:not(.problem-column) { background: rgba(35, 131, 226, .06); }
  td.is-ac { background: var(--tag-tools-bg); color: var(--cat-tools); }
  td.is-first-ac { background: rgba(15, 123, 108, .24); color: var(--cat-tools); font-weight: 650; }
  td.is-wa { background: var(--tag-research-bg); color: var(--cat-research); }
  td.is-partial { background: var(--tag-course-bg); color: var(--cat-course); }
}
.rank-column { width: 48px; color: var(--color-text-muted); }
.user-column { min-width: 200px; text-align: left !important; }
.user-name { color: var(--color-text); font-weight: 600; }
.score-column { width: 90px; strong { color: var(--color-text); font-size: 14px; font-weight: 600; } }
.problem-column { min-width: 64px; }
.role-chip {
  display: inline-flex;
  height: 20px;
  align-items: center;
  margin-left: 8px;
  padding: 0 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .01em;
  vertical-align: middle;
}
.role-chip.is-author { background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
.role-chip.is-creator { background: var(--tag-recommend-bg); color: var(--cat-recommend); }
.role-chip.is-organizer { background: var(--tag-course-bg); color: var(--cat-course); }
.cell-time { display: block; line-height: 1.2; }
.cell-tries { display: block; font-size: 11px; line-height: 1.2; opacity: .85; }
.prep-rank-empty { height: 72px !important; color: var(--color-text-faint); }
</style>
