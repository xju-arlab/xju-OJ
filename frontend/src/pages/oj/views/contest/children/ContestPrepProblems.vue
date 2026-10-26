<template>
  <section class="prep-panel" :aria-label="$t('m.Prep_Problem_List')">
    <div ref="list" :class="['prep-problem-list', { 'has-handle': canEditPrep, 'is-sorting': draggingId !== null }]" role="table">
      <div class="prep-problem-row is-head" role="row">
        <span v-if="canEditPrep" role="columnheader" :aria-label="$t('m.Prep_Drag_To_Reorder')"></span>
        <span role="columnheader">#</span>
        <span role="columnheader">{{ $t('m.Title') }}</span>
        <span role="columnheader">{{ $t('m.Prep_Feedback') }}</span>
        <span class="cell-author" role="columnheader">{{ $t('m.Prep_Author') }}</span>
        <span role="columnheader"></span>
      </div>

      <template v-for="(problem, index) in problems" :key="problem.id">
      <!-- The selected problems are the contest; the rest wait as candidates. -->
      <div v-if="groupStartsAt(index)" class="prep-problem-group" role="presentation">
        <span>{{ problem.visible ? $t('m.Prep_Group_Selected') : $t('m.Prep_Group_Candidates') }}</span>
        <small>{{ groupCount(problem.visible) }}</small>
      </div>
      <div :ref="el => setRowRef(problem.id, el)"
           :class="['prep-problem-row', {
             'is-candidate': !problem.visible,
             'is-dragging': draggingId === problem.id,
             'is-settling': settlingId === problem.id,
             'is-flash': flashId === problem.id
           }]"
           role="row">
        <span v-if="canEditPrep" class="cell-handle">
          <button type="button" class="drag-handle"
                  :aria-label="$t('m.Prep_Drag_To_Reorder')" :title="$t('m.Prep_Drag_To_Reorder')"
                  @pointerdown="startDrag($event, problem)"
                  @keydown="onHandleKey($event, index)">
            <Icon type="grip" />
          </button>
        </span>
        <span class="cell-label"><strong>{{ labelFor(problem, index) }}</strong></span>
        <span class="cell-title">
          <router-link :to="{ name: 'contest-problem-details', params: { contestID, problemID: problem._id } }">{{ problem.title }}</router-link>
          <span v-if="!problem.test_case_id && problem.judge_mode !== 'REMOTE'" class="problem-warning">{{ $t('m.Prep_No_Test_Data') }}</span>
        </span>
        <span class="cell-feedback">
          <router-link v-if="problem.feedback_count" class="feedback-count"
                       :to="{ name: 'contest-problem-details', params: { contestID, problemID: problem._id } }">{{ problem.feedback_count }}</router-link>
          <span v-else class="feedback-none">—</span>
        </span>
        <span class="cell-author">{{ problem.created_by && problem.created_by.username }}</span>
        <span class="cell-actions">
          <el-button v-if="canEditPrep" text size="small" @click="editProblem(problem)">{{ $t('m.Edit') }}</el-button>
          <a v-if="problem.test_case_id" class="download-link" :href="testCaseUrl(problem)">{{ $t('m.Prep_Test_Data') }}</a>
          <el-button v-if="canEditPrep" text type="danger" size="small" @click="deleteProblem(problem)">{{ $t('m.Delete') }}</el-button>
        </span>
      </div>
      </template>

      <p v-if="!loading && !problems.length" class="prep-empty">{{ $t('m.Prep_No_Problems') }}</p>
    </div>
  </section>
</template>

<script>
import api from '@oj/api'
import { mapGetters } from '@/store/compat'

// Rows glide a little slower than a typical UI transition so a reorder is easy to follow.
const MOVE_MS = 340
const SETTLE_MS = 300
const FLASH_MS = 1200
const EASE = 'cubic-bezier(.2, .8, .2, 1)'
const HISTORY_LIMIT = 50
const SCROLL_EDGE = 64

function alphabeticLabel (index) {
  let value = index + 1
  let label = ''
  while (value > 0) {
    value -= 1
    label = String.fromCharCode(65 + (value % 26)) + label
    value = Math.floor(value / 26)
  }
  return label
}

const sameOrder = (a, b) => a.length === b.length && a.every((id, index) => id === b[index])
const sameSet = (a, b) => a.length === b.length && a.every(id => b.includes(id))

export default {
  name: 'ContestPrepProblems',
  data () {
    return {
      loading: false,
      problems: [],
      draggingId: null,
      settlingId: null,
      flashId: null,
      pendingSaves: 0
    }
  },
  computed: {
    ...mapGetters(['canEditPrep']),
    contestID () {
      return this.$route.params.contestID
    },
    problemCount () {
      return this.$store.state.contest.contest.prep_problem_count || null
    }
  },
  created () {
    // Plain fields: per-frame pointer state must not trigger re-renders.
    this.rowEls = new Map()
    this.pointer = null
    this.frame = 0
    this.scrollFrame = 0
    this.reordering = false
    this.undoStack = []
    this.redoStack = []
    this.saveChain = Promise.resolve()
    this.timers = new Set()
  },
  mounted () {
    this.load()
    window.addEventListener('keydown', this.onKeydown)
  },
  beforeUnmount () {
    window.removeEventListener('keydown', this.onKeydown)
    this.stopPointerTracking()
    this.timers.forEach(clearTimeout)
  },
  methods: {
    setRowRef (id, el) {
      if (el) this.rowEls.set(id, el)
      else this.rowEls.delete(id)
    },
    order () {
      return this.problems.map(problem => problem.id)
    },
    groupStartsAt (index) {
      return index === 0 || this.problems[index - 1].visible !== this.problems[index].visible
    },
    groupCount (selected) {
      const count = this.problems.filter(problem => problem.visible === selected).length
      return selected && this.problemCount ? `${count} / ${this.problemCount}` : count
    },
    labelFor (problem, index) {
      // While an order is in flight, show the labels the server is about to assign.
      return this.draggingId !== null || this.pendingSaves ? alphabeticLabel(index) : problem._id
    },
    reflow () {
      return this.$refs.list ? this.$refs.list.offsetHeight : 0
    },
    duration (ms) {
      return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : ms
    },
    later (callback, ms) {
      const timer = setTimeout(() => {
        this.timers.delete(timer)
        callback()
      }, ms)
      this.timers.add(timer)
    },
    async load () {
      this.loading = true
      const previous = this.order()
      try {
        const res = await api.getPrepProblems(this.contestID)
        this.problems = res.data.data
      } catch (_) {
        this.problems = []
      } finally {
        this.loading = false
      }
      // History only holds orders of the same problem set.
      if (!sameSet(previous, this.order())) this.clearHistory()
    },
    testCaseUrl (problem) {
      return `/api/contest/prep/test_case?contest_id=${this.contestID}&problem_id=${problem.id}`
    },
    editProblem (problem) {
      this.$router.push({ name: 'contest-prep-problem-edit', params: { contestID: this.contestID, problemId: problem.id } })
    },
    deleteProblem (problem) {
      this.$confirm(this.$t('m.Prep_Delete_Problem_Confirm', { title: problem.title }), this.$t('m.Delete'), {
        type: 'warning'
      }).then(async () => {
        await api.deletePrepProblem(this.contestID, problem.id)
        await this.load()
      }).catch(() => {})
    },

    // FLIP: rows start from where they are drawn now and glide to their new slots.
    async applyOrder (ids, excludeId = null) {
      const before = new Map()
      this.rowEls.forEach((el, id) => {
        if (id !== excludeId) before.set(id, el.getBoundingClientRect().top)
      })
      const byId = new Map(this.problems.map(problem => [problem.id, problem]))
      this.problems = ids.map(id => byId.get(id))
      await this.$nextTick()
      const moved = []
      before.forEach((top, id) => {
        const el = this.rowEls.get(id)
        if (!el) return
        el.style.transition = 'none'
        el.style.transform = ''
        moved.push([el, top])
      })
      const deltas = moved.map(([el, top]) => [el, top - el.getBoundingClientRect().top])
      deltas.forEach(([el, delta]) => {
        if (delta) el.style.transform = `translate3d(0, ${delta}px, 0)`
      })
      // Commit the inverted positions before animating them away.
      this.reflow()
      const ms = this.duration(MOVE_MS)
      deltas.forEach(([el, delta]) => {
        if (!delta) return
        el.style.transition = `transform ${ms}ms ${EASE}`
        el.style.transform = ''
      })
    },

    startDrag (event, problem) {
      if (!this.canEditPrep || event.button !== 0 || this.draggingId !== null) return
      const row = this.rowEls.get(problem.id)
      if (!row) return
      event.preventDefault()
      const rect = row.getBoundingClientRect()
      this.pointer = {
        id: event.pointerId,
        clientY: event.clientY,
        grabOffset: event.clientY - rect.top,
        height: rect.height,
        startOrder: this.order()
      }
      this.draggingId = problem.id
      row.style.transition = 'box-shadow .2s ease'
      window.addEventListener('pointermove', this.onPointerMove)
      window.addEventListener('pointerup', this.onPointerUp)
      window.addEventListener('pointercancel', this.onPointerUp)
      document.body.classList.add('prep-sorting')
      this.positionDragged()
      this.scrollFrame = requestAnimationFrame(this.autoScroll)
    },
    onPointerMove (event) {
      if (!this.pointer || event.pointerId !== this.pointer.id) return
      this.pointer.clientY = event.clientY
      if (!this.frame) this.frame = requestAnimationFrame(this.updateDrag)
    },
    positionDragged () {
      const row = this.rowEls.get(this.draggingId)
      if (!row || !this.pointer) return
      const layoutTop = this.$refs.list.getBoundingClientRect().top + row.offsetTop
      const dy = this.pointer.clientY - this.pointer.grabOffset - layoutTop
      row.style.transform = `translate3d(0, ${dy}px, 0) scale(1.01)`
    },
    updateDrag () {
      this.frame = 0
      if (!this.pointer) return
      this.positionDragged()
      if (this.reordering) return
      const listTop = this.$refs.list.getBoundingClientRect().top
      const center = this.pointer.clientY - this.pointer.grabOffset - listTop + this.pointer.height / 2
      // A row moves within its own group; selecting happens on the selection tab.
      const dragged = this.problems.find(problem => problem.id === this.draggingId)
      const group = this.problems.filter(problem => problem.visible === dragged.visible)
      const others = group.filter(problem => problem.id !== this.draggingId)
      let index = 0
      others.forEach(problem => {
        const el = this.rowEls.get(problem.id)
        if (el && center > el.offsetTop + el.offsetHeight / 2) index += 1
      })
      if (index === group.indexOf(dragged)) return
      const groupIds = others.map(problem => problem.id)
      groupIds.splice(index, 0, this.draggingId)
      const rest = this.problems.filter(problem => problem.visible !== dragged.visible).map(problem => problem.id)
      const ids = dragged.visible ? [...groupIds, ...rest] : [...rest, ...groupIds]
      this.reordering = true
      this.applyOrder(ids, this.draggingId).then(() => {
        this.reordering = false
        this.positionDragged()
      })
    },
    autoScroll () {
      if (!this.pointer) return
      const y = this.pointer.clientY
      let step = 0
      if (y < SCROLL_EDGE) step = -Math.ceil((SCROLL_EDGE - y) / 5)
      else if (y > window.innerHeight - SCROLL_EDGE) step = Math.ceil((y - window.innerHeight + SCROLL_EDGE) / 5)
      if (step) {
        window.scrollBy(0, step)
        this.updateDrag()
      }
      this.scrollFrame = requestAnimationFrame(this.autoScroll)
    },
    stopPointerTracking () {
      window.removeEventListener('pointermove', this.onPointerMove)
      window.removeEventListener('pointerup', this.onPointerUp)
      window.removeEventListener('pointercancel', this.onPointerUp)
      document.body.classList.remove('prep-sorting')
      cancelAnimationFrame(this.frame)
      cancelAnimationFrame(this.scrollFrame)
      this.frame = this.scrollFrame = 0
    },
    onPointerUp (event) {
      if (!this.pointer || event.pointerId !== this.pointer.id) return
      const id = this.draggingId
      const startOrder = this.pointer.startOrder
      this.stopPointerTracking()
      this.pointer = null
      const finalOrder = this.order()
      const changed = !sameOrder(finalOrder, startOrder)
      // Save before releasing the row so the labels never flash back.
      if (changed) this.commit(startOrder, finalOrder)
      this.draggingId = null
      const row = this.rowEls.get(id)
      if (row) {
        const ms = this.duration(SETTLE_MS)
        this.settlingId = id
        row.style.transition = `transform ${ms}ms ${EASE}, box-shadow ${ms}ms ease`
        row.style.transform = ''
        this.later(() => {
          if (this.settlingId === id) this.settlingId = null
        }, ms)
      }
      if (changed) this.flash(id)
    },
    flash (id) {
      this.flashId = null
      this.$nextTick(() => {
        this.flashId = id
        this.later(() => {
          if (this.flashId === id) this.flashId = null
        }, FLASH_MS)
      })
    },
    onHandleKey (event, index) {
      const offset = { ArrowUp: -1, ArrowDown: 1 }[event.key]
      if (!offset || !this.canEditPrep) return
      event.preventDefault()
      const target = index + offset
      if (target < 0 || target >= this.problems.length || this.draggingId !== null) return
      if (this.problems[target].visible !== this.problems[index].visible) return
      const previous = this.order()
      const ids = previous.slice()
      const [id] = ids.splice(index, 1)
      ids.splice(target, 0, id)
      this.commit(previous, ids)
      this.applyOrder(ids).then(() => {
        const handle = this.rowEls.get(id) && this.rowEls.get(id).querySelector('.drag-handle')
        if (handle) handle.focus()
      })
      this.flash(id)
    },

    // History and saving. Every save sends the complete order; saves run one at a time.
    clearHistory () {
      this.undoStack = []
      this.redoStack = []
    },
    commit (previous, next) {
      this.undoStack.push(previous)
      if (this.undoStack.length > HISTORY_LIMIT) this.undoStack.shift()
      this.redoStack = []
      this.save(next)
    },
    save (ids) {
      this.pendingSaves += 1
      this.saveChain = this.saveChain.then(async () => {
        let failed = false
        try {
          const res = await api.reorderPrepProblems(this.contestID, ids)
          // With no newer save queued, the server's list wins: usually only the
          // labels change, but a pick made in another tab may regroup the rows.
          if (this.pendingSaves === 1) {
            if (!sameOrder(res.data.data.map(problem => problem.id), this.order())) this.clearHistory()
            this.problems = res.data.data
          }
        } catch (_) {
          failed = true
        } finally {
          this.pendingSaves -= 1
        }
        if (failed) await this.load()
      })
    },
    stepHistory (from, to, message) {
      if (this.draggingId !== null || !from.length) return
      const current = this.order()
      const target = from.pop()
      if (!sameSet(target, current)) {
        this.clearHistory()
        return
      }
      to.push(current)
      this.applyOrder(target)
      this.save(target)
      this.$success(this.$t(message))
    },
    onKeydown (event) {
      if (!this.canEditPrep || event.altKey || !(event.metaKey || event.ctrlKey)) return
      const target = event.target
      if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return
      const key = event.key.toLowerCase()
      const redo = (key === 'z' && event.shiftKey) || (key === 'y' && event.ctrlKey && !event.metaKey)
      if (key !== 'z' && !redo) return
      event.preventDefault()
      if (redo) this.stepHistory(this.redoStack, this.undoStack, 'm.Prep_Order_Redone')
      else this.stepHistory(this.undoStack, this.redoStack, 'm.Prep_Order_Undone')
    }
  }
}
</script>

<style scoped lang="less">
@import "@/styles/contest-prep.less";

.prep-problem-list {
  --prep-columns: 52px minmax(0, 1fr) 72px 130px 190px;
  position: relative;
  font-size: 13px;
  &.has-handle { --prep-columns: 34px 52px minmax(0, 1fr) 72px 130px 190px; }
}
.prep-problem-group {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 16px 12px 6px;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .02em;
  small { color: var(--color-text-faint); font-weight: 500; font-variant-numeric: tabular-nums; }
}
.prep-problem-row {
  position: relative;
  display: grid;
  grid-template-columns: var(--prep-columns);
  align-items: center;
  min-height: 50px;
  padding: 0 6px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
  will-change: transform;
  &:last-of-type { border-bottom: 0; }
  > span { min-width: 0; padding: 0 6px; }
  &:not(.is-head):hover { background: var(--bg-hover); }
  &.is-head {
    min-height: 38px;
    color: var(--color-text-muted);
    font-weight: 600;
    will-change: auto;
    &:hover { background: var(--color-bg); }
  }
}
.prep-problem-row.is-dragging,
.prep-problem-row.is-dragging:hover {
  z-index: 3;
  border-bottom-color: transparent;
  border-radius: 8px;
  background: var(--color-bg);
  box-shadow: 0 14px 30px rgba(15, 15, 15, .14), 0 3px 8px rgba(15, 15, 15, .08), 0 0 0 1px rgba(15, 15, 15, .06);
  cursor: grabbing;
  .drag-handle { opacity: 1; color: var(--color-text); cursor: grabbing; }
}
.prep-problem-row.is-settling { z-index: 2; }
.prep-problem-row.is-flash { animation: prep-row-flash 1.2s ease-out; }
.prep-problem-list.is-sorting .prep-problem-row:not(.is-dragging):hover { background: var(--color-bg); }
@keyframes prep-row-flash {
  from { background-color: rgba(35, 131, 226, .12); }
  to { background-color: var(--color-bg); }
}

.cell-handle { display: inline-flex; justify-content: center; padding: 0 !important; }
.drag-handle {
  display: inline-flex;
  width: 24px;
  height: 30px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-faint);
  cursor: grab;
  opacity: .55;
  touch-action: none;
  transition: opacity .2s ease, background-color .2s ease, color .2s ease;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 16px; height: 16px; }
  &:hover, &:focus-visible { background: rgba(55, 53, 47, .08); color: var(--color-text); opacity: 1; }
}
.prep-problem-row:hover .drag-handle { opacity: 1; }
.cell-label strong { color: var(--color-text); font-variant-numeric: tabular-nums; }
.prep-problem-row.is-candidate .cell-label strong { color: var(--color-text-faint); font-weight: 500; }
.cell-title {
  display: flex;
  align-items: center;
  gap: 8px;
  a { overflow: hidden; color: var(--color-text); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
}
.problem-warning { flex: none; color: var(--oj-danger); font-size: 12px; }
.feedback-count {
  display: inline-flex;
  min-width: 22px;
  height: 22px;
  align-items: center;
  justify-content: center;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--tag-research-bg);
  color: var(--cat-research);
  font-size: 12px;
  font-weight: 650;
}
.feedback-none { color: var(--color-text-faint); }
.cell-author { overflow: hidden; color: var(--color-text-muted); text-overflow: ellipsis; white-space: nowrap; }
.cell-actions { display: flex; align-items: center; justify-content: flex-end; white-space: nowrap; }
.download-link { margin: 0 8px; color: var(--color-link); font-size: 12px; }

:global(body.prep-sorting) { cursor: grabbing; user-select: none; }

@media (max-width: 760px) {
  .prep-problem-list { --prep-columns: 44px minmax(0, 1fr) 56px 150px; }
  .prep-problem-list.has-handle { --prep-columns: 30px 44px minmax(0, 1fr) 56px 150px; }
  .cell-author { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .prep-problem-row.is-flash { animation: none; }
}
</style>
