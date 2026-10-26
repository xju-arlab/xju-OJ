<template>
  <section class="prep-panel" :aria-label="$t('m.Prep_Assign')">
    <div class="plan-summary">
      <div class="summary-card">
        <div class="summary-head">
          <strong>{{ $t('m.Prep_Plan_Allocation') }}</strong>
          <span class="summary-meta">{{ $t('m.Prep_Plan_Planned', { planned: items.length, total: problemCount || '—' }) }}</span>
          <span class="plan-count">
            <span>{{ $t('m.Prep_Problem_Count') }}</span>
            <el-input-number v-if="canManagePrep" v-model="countDraft" :min="1" :max="500" size="small"
                             :disabled="savingCount" controls-position="right"
                             :placeholder="$t('m.Prep_Count_Unset')" @change="saveCount"></el-input-number>
            <b v-else>{{ problemCount || $t('m.Prep_Count_Unset') }}</b>
          </span>
        </div>
        <div class="plan-bar" role="img" :aria-label="allocationLabel">
          <span v-for="segment in allocation" :key="segment.key" :class="['plan-segment', `is-${segment.key}`]"
                :style="{ flexGrow: segment.count }" :title="`${segment.label} ${segment.count}`"></span>
        </div>
        <div class="plan-legend">
          <span v-for="segment in allocation" :key="segment.key" :class="['legend-item', `is-${segment.key}`]">
            <i></i>{{ segment.label }}<b>{{ segment.count }}</b>
          </span>
        </div>
      </div>

      <div class="summary-card">
        <div class="summary-head">
          <strong>{{ $t('m.Prep_Plan_Progress') }}</strong>
          <span class="summary-meta">{{ $t('m.Prep_Plan_Uploaded', { uploaded: totalUploaded, total: items.length }) }}</span>
        </div>
        <div class="plan-bar" role="img" :aria-label="$t('m.Prep_Plan_Progress')">
          <span v-for="row in progress" :key="row.key" class="plan-person"
                :style="{ flexGrow: row.width, '--person': row.color }" :title="row.title">
            <span class="plan-person-fill" :style="{ width: `${row.fill * 100}%` }"></span>
          </span>
        </div>
        <div class="plan-legend">
          <span v-for="row in progress" :key="row.key" :class="['legend-item', { 'is-done': row.done }]"
                :style="{ '--person': row.color }">
            <i></i>{{ row.name }}<b>{{ row.key === 'unassigned' ? row.assigned : `${row.uploaded}/${row.assigned}` }}</b>
            <Icon v-if="row.done" type="check" />
          </span>
        </div>
      </div>
    </div>

    <datalist :id="tagListId">
      <option v-for="name in tagOptions" :key="name" :value="name"></option>
    </datalist>

    <div class="plan-columns">
      <section v-for="level in levels" :key="level" :class="['plan-column', `is-${level.toLowerCase()}`]">
        <header class="plan-column-head">
          <span class="level-dot" aria-hidden="true"></span>
          <h3>{{ $t(`m.${level}`) }}</h3>
          <span class="column-count">{{ itemsOf(level).length }}</span>
        </header>

        <TransitionGroup name="plan-item" tag="ul" class="plan-items">
          <li v-for="item in itemsOf(level)" :key="item.id" class="plan-item">
            <div class="plan-item-top">
              <el-dropdown trigger="click" placement="bottom-start" @command="value => assign(item, value)">
                <button type="button" :class="['assignee', { 'is-empty': !item.assignee }]"
                        :style="item.assignee ? { '--person': memberColor(item.assignee.id) } : null">
                  <span class="assignee-avatar">{{ item.assignee ? initial(item.assignee) : '?' }}</span>
                  <span class="assignee-name">{{ item.assignee ? displayName(item.assignee) : $t('m.Prep_Plan_Unassigned') }}</span>
                  <Icon type="arrow-down-b" />
                </button>
                <template #dropdown>
                  <el-dropdown-menu class="plan-member-menu">
                    <el-dropdown-item v-for="member in team" :key="member.id" :command="member.id"
                                      :class="{ 'is-current': item.assignee && item.assignee.id === member.id }">
                      <span class="menu-dot" :style="{ background: memberColor(member.id) }"></span>
                      {{ memberLabel(member) }}
                    </el-dropdown-item>
                    <el-dropdown-item v-if="item.assignee" command="none" divided>{{ $t('m.Prep_Plan_Release') }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <button v-if="!item.assignee && canClaim" type="button" class="plan-claim"
                      @click="assign(item, me)">{{ $t('m.Prep_Plan_Claim') }}</button>
              <el-dropdown trigger="click" placement="bottom-end" @command="command => onCommand(item, command)">
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

            <div class="plan-tags">
              <span v-for="tag in item.tags" :key="tag" class="tag-chip">
                {{ tag }}
                <button type="button" class="tag-remove" :aria-label="$t('m.Delete')" @click="removeTag(item, tag)">
                  <Icon type="close" />
                </button>
              </span>
              <!-- Type a tag and press Enter (or comma); existing tags are suggested, new ones are created. -->
              <input v-if="editingTags === item.id" :ref="el => setTagInput(item.id, el)" v-model="tagDraft"
                     class="tag-input" :list="tagListId" maxlength="32" :placeholder="$t('m.Prep_Plan_Tag_Placeholder')"
                     @keydown.enter.prevent="commitTag(item)" @keydown="onTagKey($event, item)" @blur="finishTags(item)">
              <button v-else type="button" class="tag-add" @click="startTags(item)">
                <Icon type="plus" />{{ $t('m.Prep_Plan_Tags') }}
              </button>
            </div>
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
      editingTags: null,
      tagDraft: '',
      levels: LEVELS,
      tagListId: `plan-tags-${Math.random().toString(36).slice(2, 8)}`
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
    colors () {
      return new Map(this.members.map((member, index) => [member.id, PERSON_COLORS[index % PERSON_COLORS.length]]))
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
        .map(member => {
          const count = assigned.get(member.id) || 0
          return {
            key: member.id,
            name: this.displayName(member),
            assigned: count,
            uploaded: member.uploaded,
            width: Math.max(count, member.uploaded, 1),
            fill: count ? Math.min(member.uploaded / count, 1) : 1,
            done: count > 0 && member.uploaded >= count,
            color: this.memberColor(member.id),
            title: `${this.memberLabel(member)} ${member.uploaded}/${count}`
          }
        })
      if (unassigned) {
        rows.push({ key: 'unassigned', name: this.$t('m.Prep_Plan_Unassigned'), assigned: unassigned, uploaded: 0,
          width: unassigned, fill: 0, done: false, color: 'rgba(55, 53, 47, .32)', title: this.$t('m.Prep_Plan_Unassigned') })
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
  created () {
    this.tagInputs = new Map()
  },
  mounted () {
    this.load()
    api.getProblemTagList().then(res => {
      this.libraryTags = (res.data.data || []).map(tag => tag.name)
    }).catch(() => {})
    window.addEventListener(PREP_PLAN_CHANGED_EVENT, this.onPlanEvent)
  },
  beforeUnmount () {
    window.removeEventListener(PREP_PLAN_CHANGED_EVENT, this.onPlanEvent)
  },
  methods: {
    itemsOf (level) {
      return this.items.filter(item => item.difficulty === level)
    },
    displayName (person) {
      return person.real_name || person.username
    },
    initial (person) {
      return Array.from(this.displayName(person))[0].toUpperCase()
    },
    memberLabel (member) {
      return member.real_name ? `${member.real_name} · ${member.username}` : member.username
    },
    memberColor (id) {
      return this.colors.get(id) || PERSON_COLORS[0]
    },
    changed () {
      window.dispatchEvent(new CustomEvent(PREP_PLAN_CHANGED_EVENT))
    },
    onPlanEvent (event) {
      // Periodic and cross-tab refreshes; this page's own edits are already applied.
      if (event.detail && event.detail.remote && this.editingTags === null) this.load()
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
        this.changed()
      } catch (_) {
        await this.load()
      }
    },
    assign (item, value) {
      const assigneeId = value === 'none' ? null : value
      if ((item.assignee ? item.assignee.id : null) !== assigneeId) this.update(item, { assignee_id: assigneeId })
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
    setTagInput (id, el) {
      if (el) this.tagInputs.set(id, el)
      else this.tagInputs.delete(id)
    },
    startTags (item) {
      this.editingTags = item.id
      this.tagDraft = ''
      this.$nextTick(() => {
        const input = this.tagInputs.get(item.id)
        if (input) input.focus()
      })
    },
    onTagKey (event, item) {
      if (event.key === ',' || event.key === '，') {
        event.preventDefault()
        this.commitTag(item)
      } else if (event.key === 'Escape') {
        this.tagDraft = ''
        event.target.blur()
      } else if (event.key === 'Backspace' && !this.tagDraft && item.tags.length) {
        this.removeTag(item, item.tags[item.tags.length - 1])
      }
    },
    commitTag (item) {
      const name = this.tagDraft.trim()
      this.tagDraft = ''
      if (!name || item.tags.includes(name) || item.tags.length >= 12) return
      // Show it at once; the server answer replaces the item.
      item.tags = [...item.tags, name]
      this.update(item, { tags: item.tags })
    },
    finishTags (item) {
      this.commitTag(item)
      if (this.editingTags === item.id) this.editingTags = null
    },
    removeTag (item, tag) {
      item.tags = item.tags.filter(name => name !== tag)
      this.update(item, { tags: item.tags })
    },
    async saveCount (value) {
      const count = value || null
      if (count === this.problemCount) return
      this.savingCount = true
      try {
        await api.setPrepProblemCount(this.contestID, count)
        await this.$store.dispatch('getContest')
        this.changed()
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

.plan-summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.summary-card {
  min-width: 0;
  padding: 14px 16px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg);
}
.summary-head {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 28px;
  margin-bottom: 10px;
  > strong { color: var(--color-text); font-size: 14px; font-weight: 650; }
}
.summary-meta { color: var(--color-text-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.plan-count {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  color: var(--color-text-muted);
  font-size: 12px;
  b { color: var(--color-text); font-size: 13px; }
  :deep(.el-input-number) { width: 84px; }
  :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--color-border) inset; }
  :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px var(--line-strong) inset; }
}
.plan-bar {
  display: flex;
  gap: 3px;
  height: 10px;
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
  &.is-rest { background: repeating-linear-gradient(135deg, rgba(55, 53, 47, .12) 0 4px, rgba(55, 53, 47, .04) 4px 8px); }
}
.plan-person {
  position: relative;
  flex-basis: 0;
  min-width: 8px;
  overflow: hidden;
  background: color-mix(in srgb, var(--person) 20%, transparent);
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
  margin-top: 10px;
  color: var(--color-text-muted);
  font-size: 12px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  i { width: 8px; height: 8px; border-radius: 50%; background: var(--person, currentColor); }
  b { margin-left: 2px; color: var(--color-text); font-weight: 600; font-variant-numeric: tabular-nums; }
  &.is-low i { background: var(--cat-tools); }
  &.is-mid i { background: var(--cat-kaggle); }
  &.is-high i { background: var(--cat-research); }
  &.is-rest i { background: rgba(55, 53, 47, .22); }
  &.is-done { color: var(--cat-tools); }
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 13px; height: 13px; }
}

.plan-columns { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; align-items: start; }
.plan-column {
  --level: var(--cat-tools);
  --level-bg: var(--tag-tools-bg);
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 12px;
  border-radius: 12px;
  background: rgba(55, 53, 47, .03);
  &.is-mid { --level: var(--cat-kaggle); --level-bg: var(--tag-kaggle-bg); }
  &.is-high { --level: var(--cat-research); --level-bg: var(--tag-research-bg); }
}
.plan-column-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 4px 12px;
  h3 { margin: 0; color: var(--color-text); font-size: 14px; font-weight: 700; }
}
.level-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--level); }
.column-count {
  min-width: 20px;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--level-bg);
  color: var(--level);
  font-size: 12px;
  font-weight: 650;
  line-height: 20px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.plan-items { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; list-style: none; }
.plan-item {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 10px 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg);
  box-shadow: inset 3px 0 0 var(--level);
  transition: box-shadow .2s ease;
  &:hover { box-shadow: inset 3px 0 0 var(--level), 0 4px 14px rgba(15, 15, 15, .06); }
}
.plan-item-top { display: flex; align-items: center; gap: 6px; }
.plan-item-top > :first-child { min-width: 0; flex: 1; }

/* Plain buttons instead of form controls: no focus box, the same chip language as the tags. */
.assignee {
  --person: rgba(55, 53, 47, .35);
  display: inline-flex;
  max-width: 100%;
  height: 28px;
  align-items: center;
  gap: 7px;
  padding: 0 8px 0 3px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--color-text);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color .2s ease;
  :deep(.legacy-icon) { display: inline-flex; color: var(--color-text-faint); }
  :deep(svg) { width: 12px; height: 12px; }
  &:hover, &:focus-visible { background: rgba(55, 53, 47, .06); outline: none; }
  &.is-empty { color: var(--color-text-faint); font-weight: 500; }
}
.assignee-avatar {
  display: inline-flex;
  width: 22px;
  height: 22px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--person);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}
.assignee.is-empty .assignee-avatar { border: 1px dashed rgba(55, 53, 47, .3); background: transparent; color: var(--color-text-faint); }
.assignee-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.plan-claim {
  flex: none;
  height: 24px;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  background: var(--tag-course-bg);
  color: var(--cat-course);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  &:hover, &:focus-visible { background: rgba(217, 115, 13, .2); outline: none; }
}
.plan-more {
  display: inline-flex;
  width: 26px;
  height: 26px;
  flex: none;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-faint);
  cursor: pointer;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 15px; height: 15px; }
  &:hover, &:focus-visible { background: rgba(55, 53, 47, .08); color: var(--color-text); outline: none; }
}

.plan-tags { display: flex; min-height: 24px; flex-wrap: wrap; align-items: center; gap: 5px; }
.tag-chip {
  display: inline-flex;
  height: 22px;
  align-items: center;
  gap: 2px;
  padding: 0 4px 0 8px;
  border-radius: 6px;
  background: rgba(55, 53, 47, .06);
  color: var(--color-text);
  font-size: 12px;
}
.tag-remove {
  display: inline-flex;
  width: 16px;
  height: 16px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-faint);
  cursor: pointer;
  opacity: 0;
  transition: opacity .15s ease, background-color .15s ease;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 11px; height: 11px; }
  &:hover, &:focus-visible { background: rgba(55, 53, 47, .1); color: var(--color-text); opacity: 1; outline: none; }
}
.tag-chip:hover .tag-remove { opacity: 1; }
.tag-input {
  width: 110px;
  height: 22px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: rgba(55, 53, 47, .04);
  color: var(--color-text);
  font: inherit;
  font-size: 12px;
  outline: none;
  &::placeholder { color: var(--color-text-faint); }
}
.tag-add {
  display: inline-flex;
  height: 22px;
  align-items: center;
  gap: 3px;
  padding: 0 7px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-faint);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 11px; height: 11px; }
  &:hover, &:focus-visible { background: rgba(55, 53, 47, .06); color: var(--color-text-muted); outline: none; }
}

.plan-add {
  display: inline-flex;
  height: 36px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 8px;
  border: 1px dashed rgba(55, 53, 47, .18);
  border-radius: 10px;
  background: transparent;
  color: var(--color-text-muted);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: border-color .2s ease, color .2s ease, background-color .2s ease;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 14px; height: 14px; }
  &:hover:not(:disabled), &:focus-visible { border-color: var(--level); background: var(--color-bg); color: var(--level); outline: none; }
  &:disabled { cursor: not-allowed; opacity: .55; }
}
.plan-item-enter-active, .plan-item-leave-active { transition: opacity .25s ease, transform .3s cubic-bezier(.2, .8, .2, 1); }
.plan-item-enter-from, .plan-item-leave-to { opacity: 0; transform: translateY(-6px); }
.plan-item-move { transition: transform .3s cubic-bezier(.2, .8, .2, 1); }

:global(.plan-member-menu .el-dropdown-menu__item.is-current) { color: var(--color-link); font-weight: 600; }
:global(.plan-member-menu .menu-dot) { display: inline-block; width: 8px; height: 8px; margin-right: 8px; border-radius: 50%; }

@media (max-width: 960px) {
  .plan-summary { grid-template-columns: 1fr; }
}
@media (max-width: 860px) {
  .plan-columns { grid-template-columns: 1fr; }
}
</style>
