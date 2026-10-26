<template>
  <section class="prep-panel" :aria-label="$t('m.Prep_Assign')">
    <div class="plan-bars">
      <div class="plan-bar-block">
        <div class="plan-bar-title">
          <strong>{{ $t('m.Prep_Plan_Allocation') }}</strong>
          <span class="plan-bar-meta">{{ $t('m.Prep_Plan_Planned', { planned: items.length, total: problemCount || '—' }) }}</span>
          <span class="plan-count">
            <span>{{ $t('m.Prep_Problem_Count') }}</span>
            <el-input-number v-if="canManagePrep" v-model="countDraft" :min="1" :max="500" size="small"
                             :disabled="savingCount" controls-position="right"
                             :placeholder="$t('m.Prep_Count_Unset')" @change="saveCount"></el-input-number>
            <strong v-else>{{ problemCount || $t('m.Prep_Count_Unset') }}</strong>
          </span>
        </div>
        <div class="plan-bar" role="img" :aria-label="allocationLabel">
          <span v-for="segment in allocation" :key="segment.key"
                :class="['plan-segment', `is-${segment.key}`]"
                :style="{ flexGrow: segment.count }"
                :title="`${segment.label} ${segment.count}`"></span>
        </div>
        <div class="plan-legend">
          <span v-for="segment in allocation" :key="segment.key" :class="['legend-item', `is-${segment.key}`]">
            <i></i>{{ segment.label }} <b>{{ segment.count }}</b>
          </span>
        </div>
      </div>

      <div class="plan-bar-block">
        <div class="plan-bar-title">
          <strong>{{ $t('m.Prep_Plan_Progress') }}</strong>
          <span class="plan-bar-meta">{{ $t('m.Prep_Plan_Uploaded', { uploaded: totalUploaded, total: items.length }) }}</span>
        </div>
        <div class="plan-bar" role="img" :aria-label="$t('m.Prep_Plan_Progress')">
          <span v-for="row in progress" :key="row.key" class="plan-person"
                :style="{ flexGrow: row.width, '--person': row.color }"
                :title="row.title">
            <span class="plan-person-fill" :style="{ width: `${row.fill * 100}%` }"></span>
          </span>
        </div>
        <div class="plan-legend">
          <span v-for="row in progress" :key="row.key" :class="['legend-item', { 'is-done': row.done }]"
                :style="{ '--person': row.color }">
            <i></i>{{ row.name }} <b>{{ row.key === 'unassigned' ? row.assigned : `${row.uploaded}/${row.assigned}` }}</b>
            <Icon v-if="row.done" type="check" />
          </span>
        </div>
      </div>
    </div>

    <div class="plan-columns">
      <section v-for="level in levels" :key="level" :class="['plan-column', `is-${level.toLowerCase()}`]">
        <header class="plan-column-head">
          <span class="level-dot" aria-hidden="true"></span>
          <h3>{{ $t(`m.${level}`) }}</h3>
          <small>{{ itemsOf(level).length }}</small>
        </header>
        <TransitionGroup name="plan-item" tag="ul" class="plan-items">
          <li v-for="item in itemsOf(level)" :key="item.id" class="plan-item">
            <div class="plan-item-row">
              <el-select :model-value="item.assignee ? item.assignee.id : null" size="small" filterable clearable
                         class="plan-assignee" :placeholder="$t('m.Prep_Plan_Assignee')"
                         @change="value => update(item, { assignee_id: value || null })">
                <el-option v-for="member in team" :key="member.id" :value="member.id" :label="memberLabel(member)"></el-option>
              </el-select>
              <button v-if="!item.assignee && canClaim" type="button" class="plan-claim"
                      @click="update(item, { assignee_id: me })">{{ $t('m.Prep_Plan_Claim') }}</button>
              <el-dropdown trigger="click" @command="command => onCommand(item, command)">
                <button type="button" class="plan-more" :aria-label="$t('m.Prep_Plan_More')"><Icon type="more" /></button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-for="target in levels.filter(other => other !== level)" :key="target"
                                      :command="`move:${target}`">{{ $t('m.Prep_Plan_Move_To', { level: $t(`m.${target}`) }) }}</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>{{ $t('m.Delete') }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <el-select :model-value="item.tags" size="small" multiple filterable allow-create default-first-option
                       :reserve-keyword="false" :multiple-limit="12" class="plan-tags"
                       :placeholder="$t('m.Prep_Plan_Tags')"
                       @change="value => update(item, { tags: value })">
              <el-option v-for="name in tagOptions" :key="name" :value="name" :label="name"></el-option>
            </el-select>
          </li>
        </TransitionGroup>
        <button type="button" class="plan-add" :disabled="planFull || adding === level" @click="add(level)">
          <Icon type="plus" />{{ planFull ? $t('m.Prep_Plan_Full', { count: problemCount }) : $t('m.Prep_Plan_Add') }}
        </button>
      </section>
    </div>
  </section>
</template>

<script>
import api from '@oj/api'
import { mapGetters } from '@/store/compat'
import { PREP_PLAN_CHANGED_EVENT } from '@/utils/constants'

const LEVELS = ['Low', 'Mid', 'High']
const PERSON_COLORS = ['#2383e2', '#d9730d', '#9065b0', '#0f7b6c', '#b8405e', '#b5926a', '#0b6e99', '#e03e3e']

export default {
  name: 'ContestPrepAssign',
  data () {
    return {
      items: [],
      members: [],
      libraryTags: [],
      countDraft: undefined,
      savingCount: false,
      adding: null,
      levels: LEVELS
    }
  },
  computed: {
    ...mapGetters(['canManagePrep', 'user']),
    contestID () {
      return this.$route.params.contestID
    },
    problemCount () {
      return this.$store.state.contest.contest.prep_problem_count || null
    },
    me () {
      return this.user && this.user.id
    },
    team () {
      return this.members.filter(member => member.member)
    },
    canClaim () {
      return this.team.some(member => member.id === this.me)
    },
    planFull () {
      return Boolean(this.problemCount) && this.items.length >= this.problemCount
    },
    allocation () {
      const segments = LEVELS.map(level => ({
        key: level.toLowerCase(), label: this.$t(`m.${level}`), count: this.itemsOf(level).length
      }))
      if (this.problemCount && this.items.length < this.problemCount) {
        segments.push({ key: 'rest', label: this.$t('m.Prep_Plan_Unplanned'), count: this.problemCount - this.items.length })
      }
      return segments
    },
    allocationLabel () {
      return this.allocation.map(segment => `${segment.label} ${segment.count}`).join(', ')
    },
    // One segment per person, as wide as their share of the plan, filled by what they uploaded.
    progress () {
      const assigned = new Map()
      let unassigned = 0
      this.items.forEach(item => {
        if (item.assignee) assigned.set(item.assignee.id, (assigned.get(item.assignee.id) || 0) + 1)
        else unassigned += 1
      })
      const rows = this.members
        .filter(member => assigned.get(member.id) || member.uploaded)
        .map((member, index) => {
          const count = assigned.get(member.id) || 0
          return {
            key: member.id,
            name: member.real_name || member.username,
            assigned: count,
            uploaded: member.uploaded,
            width: Math.max(count, member.uploaded, 1),
            fill: count ? Math.min(member.uploaded / count, 1) : 1,
            done: count > 0 && member.uploaded >= count,
            color: PERSON_COLORS[index % PERSON_COLORS.length],
            title: `${this.memberLabel(member)} ${member.uploaded}/${count}`
          }
        })
      if (unassigned) {
        rows.push({ key: 'unassigned', name: this.$t('m.Prep_Plan_Unassigned'), assigned: unassigned, uploaded: 0,
          width: unassigned, fill: 0, done: false, color: 'rgba(55, 53, 47, .35)', title: this.$t('m.Prep_Plan_Unassigned') })
      }
      return rows
    },
    totalUploaded () {
      return this.members.reduce((sum, member) => sum + member.uploaded, 0)
    },
    tagOptions () {
      const names = new Set(this.libraryTags)
      this.items.forEach(item => item.tags.forEach(name => names.add(name)))
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
    itemsOf (level) {
      return this.items.filter(item => item.difficulty === level)
    },
    memberLabel (member) {
      return member.real_name ? `${member.username}（${member.real_name}）` : member.username
    },
    changed () {
      window.dispatchEvent(new CustomEvent(PREP_PLAN_CHANGED_EVENT))
    },
    async load () {
      try {
        const res = await api.getPrepPlan(this.contestID)
        this.items = res.data.data.items
        this.members = res.data.data.progress
      } catch (_) {
        this.items = []
      }
    },
    replace (item) {
      const index = this.items.findIndex(entry => entry.id === item.id)
      if (index >= 0) this.items.splice(index, 1, item)
    },
    async add (level) {
      this.adding = level
      try {
        const res = await api.addPrepPlanItem(this.contestID, { difficulty: level })
        this.items.push(res.data.data)
        this.changed()
      } catch (_) {
        // The API client already shows the error.
      } finally {
        this.adding = null
      }
    },
    async update (item, change) {
      try {
        const res = await api.updatePrepPlanItem(this.contestID, item.id, change)
        this.replace(res.data.data)
        if ('assignee_id' in change) this.changed()
      } catch (_) {
        await this.load()
      }
    },
    onCommand (item, command) {
      if (command === 'delete') return this.remove(item)
      if (command.startsWith('move:')) this.update(item, { difficulty: command.slice(5) })
    },
    async remove (item) {
      try {
        await api.deletePrepPlanItem(this.contestID, item.id)
        this.items = this.items.filter(entry => entry.id !== item.id)
        this.changed()
      } catch (_) {
        await this.load()
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

.plan-bars { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px 28px; margin-bottom: 22px; }
.plan-bar-block { min-width: 0; }
.plan-bar-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  min-height: 30px;
  margin-bottom: 8px;
  > strong { color: var(--color-text); font-size: 14px; }
}
.plan-bar-meta { color: var(--color-text-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.plan-count {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  color: var(--color-text-muted);
  font-size: 12px;
  :deep(.el-input-number) { width: 96px; }
  strong { color: var(--color-text); font-size: 14px; }
}
.plan-bar {
  display: flex;
  gap: 3px;
  height: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(55, 53, 47, .06);
}
.plan-segment {
  flex-basis: 0;
  min-width: 6px;
  transition: flex-grow .45s cubic-bezier(.2, .8, .2, 1);
  &.is-low { background: var(--cat-tools); }
  &.is-mid { background: var(--cat-kaggle); }
  &.is-high { background: var(--cat-research); }
  &.is-rest { background: repeating-linear-gradient(135deg, rgba(55, 53, 47, .1) 0 4px, rgba(55, 53, 47, .04) 4px 8px); }
}
.plan-person {
  position: relative;
  flex-basis: 0;
  min-width: 8px;
  overflow: hidden;
  background: color-mix(in srgb, var(--person) 22%, transparent);
  transition: flex-grow .45s cubic-bezier(.2, .8, .2, 1);
}
.plan-person-fill {
  position: absolute;
  inset: 0 auto 0 0;
  background: var(--person);
  transition: width .45s cubic-bezier(.2, .8, .2, 1);
}
.plan-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  margin-top: 8px;
  color: var(--color-text-muted);
  font-size: 12px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  i { width: 8px; height: 8px; border-radius: 50%; background: var(--person, currentColor); }
  b { color: var(--color-text); font-weight: 600; font-variant-numeric: tabular-nums; }
  &.is-low i { background: var(--cat-tools); }
  &.is-mid i { background: var(--cat-kaggle); }
  &.is-high i { background: var(--cat-research); }
  &.is-rest i { background: rgba(55, 53, 47, .2); }
  &.is-done { color: var(--cat-tools); }
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 13px; height: 13px; }
}

.plan-columns { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; align-items: start; }
.plan-column {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 12px;
  border-radius: 10px;
  background: rgba(55, 53, 47, .03);
  --level: var(--cat-tools);
  &.is-mid { --level: var(--cat-kaggle); }
  &.is-high { --level: var(--cat-research); }
}
.plan-column-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 4px 10px;
  h3 { margin: 0; color: var(--color-text); font-size: 14px; font-weight: 700; }
  small { color: var(--color-text-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
}
.level-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--level); }
.plan-items { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; list-style: none; }
.plan-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--level);
  border-radius: 8px;
  background: var(--color-bg);
  transition: box-shadow .2s ease, border-color .2s ease;
  &:hover { box-shadow: 0 2px 10px rgba(15, 15, 15, .06); }
}
.plan-item-row { display: flex; align-items: center; gap: 6px; }
.plan-assignee { flex: 1; min-width: 0; }
.plan-tags { width: 100%; }
.plan-claim {
  flex: none;
  height: 24px;
  padding: 0 9px;
  border: 0;
  border-radius: 999px;
  background: var(--tag-course-bg);
  color: var(--cat-course);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  &:hover, &:focus-visible { background: rgba(217, 115, 13, .2); }
}
.plan-more {
  display: inline-flex;
  width: 26px;
  height: 26px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-faint);
  cursor: pointer;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 15px; height: 15px; }
  &:hover, &:focus-visible { background: rgba(55, 53, 47, .08); color: var(--color-text); }
}
.plan-add {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 34px;
  margin-top: 8px;
  border: 1px dashed var(--color-border);
  border-radius: 8px;
  background: transparent;
  color: var(--color-text-muted);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: border-color .2s ease, color .2s ease, background-color .2s ease;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 14px; height: 14px; }
  &:hover:not(:disabled), &:focus-visible { border-color: var(--level); background: var(--color-bg); color: var(--level); }
  &:disabled { cursor: not-allowed; opacity: .6; }
}
.plan-item-enter-active, .plan-item-leave-active { transition: opacity .25s ease, transform .3s cubic-bezier(.2, .8, .2, 1); }
.plan-item-enter-from, .plan-item-leave-to { opacity: 0; transform: translateY(-6px); }
.plan-item-move { transition: transform .3s cubic-bezier(.2, .8, .2, 1); }

@media (max-width: 960px) {
  .plan-bars { grid-template-columns: 1fr; }
}
@media (max-width: 860px) {
  .plan-columns { grid-template-columns: 1fr; }
}
</style>
