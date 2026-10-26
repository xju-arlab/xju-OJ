<template>
  <section class="prep-panel" :aria-label="$t('m.Prep_Select')">
    <div class="select-summary">
      <div class="summary-count">
        <span class="summary-label">{{ $t('m.Prep_Problem_Count') }}</span>
        <el-input-number v-if="canManagePrep" v-model="countDraft" :min="1" :max="500" size="small"
                         :disabled="savingCount" controls-position="right"
                         :placeholder="$t('m.Prep_Count_Unset')"
                         @change="saveCount"></el-input-number>
        <strong v-else>{{ problemCount || $t('m.Prep_Count_Unset') }}</strong>
      </div>
      <div class="summary-progress" :class="{ 'is-full': isFull }">
        <span class="summary-label">{{ $t('m.Prep_Selected') }}</span>
        <strong>{{ selected.length }}<small v-if="problemCount"> / {{ problemCount }}</small></strong>
        <span v-if="problemCount" class="progress-track" aria-hidden="true">
          <span class="progress-fill" :style="{ width: `${Math.min(selected.length / problemCount, 1) * 100}%` }"></span>
        </span>
      </div>
      <div v-if="selected.length" class="summary-mix">
        <span v-for="level in difficulties" :key="level" v-show="difficultyMix[level]"
              :class="['level-chip', `level-${level.toLowerCase()}`]">{{ $t(`m.${level}`) }} {{ difficultyMix[level] }}</span>
        <span v-for="item in topicMix" :key="item.name" class="topic-chip">{{ item.name }}<small>{{ item.count }}</small></span>
      </div>
    </div>

    <div :class="['select-list', { 'is-busy': busyId !== null }]" role="table">
      <div class="select-row is-head" role="row">
        <span role="columnheader"><span class="sr-only">{{ $t('m.Prep_Selected') }}</span></span>
        <span role="columnheader">#</span>
        <span role="columnheader">{{ $t('m.Title') }}</span>
        <span role="columnheader">{{ $t('m.Difficulty') }}</span>
        <span role="columnheader">{{ $t('m.Prep_Knowledge_Points') }}</span>
        <span class="cell-author" role="columnheader">{{ $t('m.Prep_Author') }}</span>
      </div>

      <TransitionGroup name="select-row" tag="div" class="select-body">
        <div v-for="item in rows" :key="item.key"
             :class="item.group ? ['select-group', `is-${item.group}`] : ['select-row', {
               'is-selected': item.problem.visible,
               'is-incomplete': isIncomplete(item.problem)
             }]"
             :role="item.group ? 'presentation' : 'row'">
          <template v-if="item.group">
            <span>{{ item.group === 'selected' ? $t('m.Prep_Group_Selected') : $t('m.Prep_Group_Candidates') }}</span>
            <small>{{ item.count }}</small>
          </template>
          <template v-else>
            <span class="cell-check">
              <el-tooltip :disabled="!blockReason(item.problem)" :content="blockReason(item.problem)" placement="top">
                <span>
                  <el-checkbox :model-value="item.problem.visible"
                               :disabled="busyId !== null || Boolean(blockReason(item.problem))"
                               :aria-label="item.problem.title"
                               @change="value => toggle(item.problem, value)"></el-checkbox>
                </span>
              </el-tooltip>
            </span>
            <span :class="['cell-label', { 'is-candidate': !item.problem.visible }]"><strong>{{ item.problem._id }}</strong></span>
            <span class="cell-title">
              <router-link :to="{ name: 'contest-problem-details', params: { contestID, problemID: item.problem._id } }">{{ item.problem.title }}</router-link>
              <span v-if="isIncomplete(item.problem)" class="incomplete-hint">{{ $t('m.Prep_Fill_Meta') }}</span>
            </span>
            <span class="cell-difficulty">
              <el-select :model-value="item.problem.difficulty" size="small" :disabled="savingId === item.problem.id"
                         @change="value => saveMeta(item.problem, { difficulty: value })">
                <el-option v-for="level in difficulties" :key="level" :value="level" :label="$t(`m.${level}`)"></el-option>
              </el-select>
            </span>
            <span :class="['cell-tags', { 'is-missing': !tagsOf(item.problem).length }]">
              <el-select :model-value="tagsOf(item.problem)" size="small" multiple filterable allow-create
                         default-first-option :reserve-keyword="false" :multiple-limit="12"
                         :placeholder="$t('m.Prep_Add_Knowledge_Point')"
                         :disabled="savingId === item.problem.id"
                         @change="value => saveMeta(item.problem, { tags: value })">
                <el-option v-for="name in tagOptions" :key="name" :value="name" :label="name"></el-option>
              </el-select>
            </span>
            <span class="cell-author">{{ item.problem.created_by && item.problem.created_by.username }}</span>
          </template>
        </div>
      </TransitionGroup>

      <p v-if="!loading && !problems.length" class="prep-empty">{{ $t('m.Prep_No_Problems') }}</p>
    </div>
  </section>
</template>

<script>
import api from '@oj/api'
import { mapGetters } from '@/store/compat'

const DIFFICULTIES = ['Low', 'Mid', 'High']
const TOPIC_CHIPS = 8

export default {
  name: 'ContestPrepSelect',
  data () {
    return {
      loading: false,
      problems: [],
      libraryTags: [],
      countDraft: undefined,
      savingCount: false,
      busyId: null,
      savingId: null,
      difficulties: DIFFICULTIES
    }
  },
  computed: {
    ...mapGetters(['canManagePrep']),
    contestID () {
      return this.$route.params.contestID
    },
    problemCount () {
      return this.$store.state.contest.contest.prep_problem_count || null
    },
    selected () {
      return this.problems.filter(problem => problem.visible)
    },
    candidates () {
      return this.problems.filter(problem => !problem.visible)
    },
    isFull () {
      return Boolean(this.problemCount) && this.selected.length >= this.problemCount
    },
    // Group headings travel with the rows, so a pick glides across the divider.
    rows () {
      const rows = []
      if (this.selected.length) {
        rows.push({ key: 'group-selected', group: 'selected', count: this.problemCount ? `${this.selected.length} / ${this.problemCount}` : this.selected.length })
        this.selected.forEach(problem => rows.push({ key: problem.id, problem }))
      }
      if (this.candidates.length) {
        rows.push({ key: 'group-candidates', group: 'candidates', count: this.candidates.length })
        this.candidates.forEach(problem => rows.push({ key: problem.id, problem }))
      }
      return rows
    },
    difficultyMix () {
      const mix = {}
      this.selected.forEach(problem => { mix[problem.difficulty] = (mix[problem.difficulty] || 0) + 1 })
      return mix
    },
    topicMix () {
      const counts = new Map()
      this.selected.forEach(problem => this.tagsOf(problem).forEach(name => counts.set(name, (counts.get(name) || 0) + 1)))
      return [...counts].map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)).slice(0, TOPIC_CHIPS)
    },
    tagOptions () {
      const names = new Set(this.libraryTags)
      this.problems.forEach(problem => this.tagsOf(problem).forEach(name => names.add(name)))
      return [...names].sort((a, b) => a.localeCompare(b))
    }
  },
  watch: {
    problemCount: {
      immediate: true,
      handler (value) {
        this.countDraft = value || undefined
      }
    }
  },
  mounted () {
    this.load()
    api.getProblemTagList().then(res => {
      this.libraryTags = (res.data.data || []).map(tag => tag.name)
    }).catch(() => {})
  },
  methods: {
    tagsOf (problem) {
      return (problem.tags || []).map(tag => typeof tag === 'string' ? tag : tag.name)
    },
    isIncomplete (problem) {
      return !problem.difficulty || !this.tagsOf(problem).length
    },
    blockReason (problem) {
      if (problem.visible) return ''
      if (this.isIncomplete(problem)) return this.$t('m.Prep_Fill_Meta_First')
      if (this.isFull) return this.$t('m.Prep_Count_Reached', { count: this.problemCount })
      return ''
    },
    async load () {
      this.loading = true
      try {
        const res = await api.getPrepProblems(this.contestID)
        this.problems = res.data.data
      } catch (_) {
        this.problems = []
      } finally {
        this.loading = false
      }
    },
    async toggle (problem, selected) {
      this.busyId = problem.id
      try {
        const res = await api.selectPrepProblem(this.contestID, problem.id, selected)
        this.problems = res.data.data
      } catch (_) {
        await this.load()
      } finally {
        this.busyId = null
      }
    },
    async saveMeta (problem, change) {
      const difficulty = change.difficulty || problem.difficulty
      const tags = (change.tags || this.tagsOf(problem)).map(name => String(name).trim()).filter(Boolean)
      if (!tags.length) {
        // Keep the gap visible; at least one knowledge point is required.
        problem.tags = []
        return
      }
      this.savingId = problem.id
      try {
        const res = await api.updatePrepProblemMeta(this.contestID, problem.id, difficulty, tags)
        Object.assign(problem, { difficulty: res.data.data.difficulty, tags: res.data.data.tags })
      } catch (_) {
        await this.load()
      } finally {
        this.savingId = null
      }
    },
    async saveCount (value) {
      const count = value || null
      if (count === this.problemCount) return
      this.savingCount = true
      try {
        await api.setPrepProblemCount(this.contestID, count)
        await this.$store.dispatch('getContest')
      } catch (_) {
        this.countDraft = this.problemCount || undefined
      } finally {
        this.savingCount = false
      }
    }
  }
}
</script>

<style scoped lang="less">
@import "@/styles/contest-prep.less";

.select-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px 28px;
  margin-bottom: 18px;
}
.summary-label { color: var(--color-text-muted); font-size: 13px; }
.summary-count, .summary-progress { display: inline-flex; align-items: center; gap: 10px; }
.summary-count :deep(.el-input-number) { width: 110px; }
.summary-count strong, .summary-progress strong {
  color: var(--color-text);
  font-size: 15px;
  font-variant-numeric: tabular-nums;
  small { color: var(--color-text-muted); font-size: 13px; font-weight: 500; }
}
.progress-track {
  position: relative;
  width: 120px;
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(55, 53, 47, .08);
}
.progress-fill {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: inherit;
  background: var(--color-link);
  transition: width .4s cubic-bezier(.2, .8, .2, 1);
}
.summary-progress.is-full .progress-fill { background: var(--cat-tools); }
.summary-mix { display: flex; flex: 1 1 260px; flex-wrap: wrap; gap: 6px; }
.level-chip, .topic-chip {
  display: inline-flex;
  height: 22px;
  align-items: center;
  gap: 4px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.level-low { background: var(--tag-tools-bg); color: var(--cat-tools); }
.level-mid { background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
.level-high { background: var(--tag-research-bg); color: var(--cat-research); }
.topic-chip {
  background: rgba(55, 53, 47, .06);
  color: var(--color-text-muted);
  font-weight: 500;
  small { color: var(--color-text-faint); font-variant-numeric: tabular-nums; }
}

.select-list {
  --select-columns: 40px 44px minmax(0, 1.3fr) 104px minmax(0, 1.5fr) 110px;
  position: relative;
  font-size: 13px;
  &.is-busy { cursor: progress; }
}
.select-row {
  display: grid;
  grid-template-columns: var(--select-columns);
  align-items: center;
  min-height: 50px;
  padding: 6px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
  transition: background-color .25s ease;
  > span { min-width: 0; padding: 0 6px; }
  &:not(.is-head):hover { background: var(--bg-hover); }
  &.is-head { min-height: 38px; color: var(--color-text-muted); font-weight: 600; }
  &.is-selected { background: linear-gradient(90deg, rgba(35, 131, 226, .05), transparent 60%); }
  &.is-selected:hover { background: var(--bg-hover); }
}
.select-group {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 16px 12px 6px;
  color: var(--color-text);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .02em;
  small { color: var(--color-text-faint); font-weight: 500; font-variant-numeric: tabular-nums; }
  &.is-candidates { color: var(--color-text-muted); }
}
.select-row-move { transition: transform .34s cubic-bezier(.2, .8, .2, 1); }
.select-row-enter-active, .select-row-leave-active { transition: opacity .2s ease; }
.select-row-enter-from, .select-row-leave-to { opacity: 0; }
.select-row-leave-active { position: absolute; width: 100%; }

.cell-check { display: inline-flex; justify-content: center; }
.cell-label strong { color: var(--color-text); font-variant-numeric: tabular-nums; }
.cell-label.is-candidate strong { color: var(--color-text-faint); font-weight: 500; }
.cell-title {
  display: flex;
  align-items: center;
  gap: 8px;
  a { overflow: hidden; color: var(--color-text); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
}
.incomplete-hint { flex: none; color: var(--oj-warning); font-size: 12px; }
.cell-difficulty :deep(.el-select) { width: 100%; }
.cell-tags :deep(.el-select) { width: 100%; }
.cell-tags.is-missing :deep(.el-select__wrapper) { box-shadow: 0 0 0 1px rgba(217, 115, 13, .5) inset; }
.cell-author { overflow: hidden; color: var(--color-text-muted); text-overflow: ellipsis; white-space: nowrap; }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

@media (max-width: 860px) {
  .select-list { --select-columns: 36px 40px minmax(0, 1fr) 96px minmax(0, 1.2fr); }
  .cell-author { display: none; }
}
@media (max-width: 600px) {
  .select-list { --select-columns: 36px 36px minmax(0, 1fr) 92px; }
  .cell-tags, .select-row.is-head > span:nth-child(5) { display: none; }
}
</style>
