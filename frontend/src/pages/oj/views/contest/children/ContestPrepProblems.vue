<template>
  <section class="prep-panel" :aria-label="$t('m.Prep_Problem_List')">
    <table class="prep-problem-table">
      <thead>
        <tr>
          <th v-if="canEditPrep" class="drag-column" :aria-label="$t('m.Prep_Drag_To_Reorder')"></th>
          <th class="label-column">#</th>
          <th>{{ $t('m.Title') }}</th>
          <th class="visible-column">{{ $t('m.Visible') }}</th>
          <th class="feedback-column">{{ $t('m.Prep_Feedback') }}</th>
          <th class="author-column">{{ $t('m.Prep_Author') }}</th>
          <th class="actions-column"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(problem, index) in problems"
            :key="problem.id"
            :draggable="canEditPrep ? 'true' : 'false'"
            :class="{ 'is-dragging': dragIndex === index, 'is-drop-target': dropIndex === index && dragIndex !== index }"
            @dragstart="onDragStart(index, $event)"
            @dragover.prevent="dropIndex = index"
            @drop.prevent="onDrop(index)"
            @dragend="dragIndex = dropIndex = null">
          <td v-if="canEditPrep" class="drag-column">
            <span class="drag-handle" :title="$t('m.Prep_Drag_To_Reorder')"><Icon type="grip" /></span>
            <span class="move-buttons">
              <button type="button" :disabled="index === 0 || saving" :aria-label="$t('m.Prep_Move_Up')"
                      @click="move(index, index - 1)">↑</button>
              <button type="button" :disabled="index === problems.length - 1 || saving" :aria-label="$t('m.Prep_Move_Down')"
                      @click="move(index, index + 1)">↓</button>
            </span>
          </td>
          <td class="label-column"><strong>{{ problem._id }}</strong></td>
          <td class="title-column">
            <router-link :to="{ name: 'contest-problem-details', params: { contestID, problemID: problem._id } }">{{ problem.title }}</router-link>
            <span v-if="!problem.test_case_id && problem.judge_mode !== 'REMOTE'" class="problem-warning">{{ $t('m.Prep_No_Test_Data') }}</span>
          </td>
          <td class="visible-column">
            <el-switch :model-value="problem.visible" :disabled="!canEditPrep"
                       @change="value => setVisible(problem, value)"></el-switch>
          </td>
          <td class="feedback-column">
            <router-link v-if="problem.feedback_count" class="feedback-count"
                         :to="{ name: 'contest-problem-details', params: { contestID, problemID: problem._id } }">{{ problem.feedback_count }}</router-link>
            <span v-else class="feedback-none">—</span>
          </td>
          <td class="author-column">{{ problem.created_by && problem.created_by.username }}</td>
          <td class="actions-column">
            <el-button v-if="canEditPrep" text size="small" @click="editProblem(problem)">{{ $t('m.Edit') }}</el-button>
            <a v-if="problem.test_case_id" class="download-link" :href="testCaseUrl(problem)">{{ $t('m.Prep_Test_Data') }}</a>
            <el-button v-if="canEditPrep" text type="danger" size="small" @click="deleteProblem(problem)">{{ $t('m.Delete') }}</el-button>
          </td>
        </tr>
        <tr v-if="!loading && !problems.length">
          <td :colspan="canEditPrep ? 7 : 6" class="prep-empty">{{ $t('m.Prep_No_Problems') }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script>
import api from '@oj/api'
import { mapGetters } from '@/store/compat'

export default {
  name: 'ContestPrepProblems',
  data () {
    return {
      loading: false,
      saving: false,
      problems: [],
      dragIndex: null,
      dropIndex: null
    }
  },
  computed: {
    ...mapGetters(['canEditPrep']),
    contestID () {
      return this.$route.params.contestID
    }
  },
  mounted () {
    this.load()
  },
  methods: {
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
    testCaseUrl (problem) {
      return `/api/contest/prep/test_case?contest_id=${this.contestID}&problem_id=${problem.id}`
    },
    editProblem (problem) {
      this.$router.push({ name: 'contest-prep-problem-edit', params: { contestID: this.contestID, problemId: problem.id } })
    },
    async setVisible (problem, visible) {
      try {
        await api.setPrepProblemVisible(this.contestID, problem.id, visible)
        problem.visible = visible
      } catch (_) {
        // The API client already shows the error.
      }
    },
    deleteProblem (problem) {
      this.$confirm(this.$t('m.Prep_Delete_Problem_Confirm', { title: problem.title }), this.$t('m.Delete'), {
        type: 'warning'
      }).then(async () => {
        await api.deletePrepProblem(this.contestID, problem.id)
        await this.load()
      }).catch(() => {})
    },
    onDragStart (index, event) {
      if (!this.canEditPrep || this.saving) return event.preventDefault()
      this.dragIndex = index
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData('text/plain', String(index))
    },
    onDrop (index) {
      if (this.dragIndex !== null && this.dragIndex !== index) this.move(this.dragIndex, index)
      this.dragIndex = this.dropIndex = null
    },
    async move (from, to) {
      if (!this.canEditPrep || this.saving || to < 0 || to >= this.problems.length) return
      const ordered = [...this.problems]
      const [item] = ordered.splice(from, 1)
      ordered.splice(to, 0, item)
      this.problems = ordered
      this.saving = true
      try {
        // The server relabels the problems A, B, C... in this order.
        const res = await api.reorderPrepProblems(this.contestID, ordered.map(problem => problem.id))
        this.problems = res.data.data
      } catch (_) {
        await this.load()
      } finally {
        this.saving = false
      }
    }
  }
}
</script>

<style scoped lang="less">
@import "@/styles/contest-prep.less";

.prep-problem-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  th, td { padding: 10px 12px; border-bottom: 1px solid var(--color-border); text-align: left; vertical-align: middle; }
  th { color: var(--color-text-muted); font-weight: 600; }
  tr[draggable="true"] { cursor: grab; }
  tr.is-dragging { opacity: .45; }
  tr.is-drop-target td { box-shadow: inset 0 2px 0 var(--color-link); }
}
.drag-column { width: 92px; white-space: nowrap; }
.drag-handle { display: inline-flex; vertical-align: middle; color: var(--color-text-faint); }
.move-buttons button {
  width: 24px;
  height: 24px;
  margin-left: 4px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
  color: var(--color-text-muted);
  cursor: pointer;
  &:disabled { opacity: .4; cursor: default; }
}
.label-column { width: 56px; }
.title-column a { color: var(--color-text); font-weight: 600; }
.problem-warning { margin-left: 8px; color: var(--oj-danger); font-size: 12px; }
.visible-column { width: 90px; }
.feedback-column { width: 80px; }
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
.author-column { width: 130px; color: var(--color-text-muted); }
.actions-column { width: 200px; text-align: right; white-space: nowrap; }
.download-link { margin: 0 8px; color: var(--color-link); font-size: 12px; }
@media (max-width: 760px) {
  .author-column { display: none; }
  .actions-column { width: auto; }
}
</style>
