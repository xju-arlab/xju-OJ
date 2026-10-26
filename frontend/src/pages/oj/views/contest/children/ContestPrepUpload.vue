<template>
  <section class="prep-panel" :aria-label="$t('m.Prep_Upload')">
    <!-- Every member may write problems; wait for the contest so the role is known. -->
    <ProblemEditorForm v-if="canEditPrep"
                       mode="add"
                       :contest-id="contestID"
                       :service="service"
                       @saved="saved">
      <template #basic-actions>
        <el-upload :action="importAction"
                   :headers="csrfHeaders()"
                   :data="{ contest_id: contestID }"
                   name="file"
                   accept=".zip"
                   :show-file-list="false"
                   :before-upload="() => { importing = true; return true }"
                   :on-success="importSucceeded"
                   :on-error="importFailed">
          <el-button size="small" :loading="importing"><Icon type="upload" />{{ $t('m.Prep_Import_Zip') }}</el-button>
        </el-upload>
        <el-button size="small" @click="openPicker"><Icon type="search" />{{ $t('m.Prep_Select_Problem') }}</el-button>
      </template>
      <template #remarks>
        <div class="remark-heading">
          <h3>{{ $t('m.Prep_Feedback') }}</h3>
          <p>{{ $t('m.Prep_Remark_Hint') }}</p>
        </div>
        <el-input v-model="remark" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" maxlength="2000"
                  show-word-limit :placeholder="$t('m.Prep_Remark_Placeholder')" />
      </template>
    </ProblemEditorForm>

    <LegacyDialog :title="$t('m.Prep_Select_Problem')" width="720px"
                  :visible="pickerVisible" @update:visible="pickerVisible = $event">
      <el-input v-model="keyword" :placeholder="$t('m.Prep_Search_Problem')" clearable @input="searchProblems">
        <template #prefix><Icon type="search" /></template>
      </el-input>
      <table class="picker-table">
        <thead>
          <tr>
            <th class="id-column">#</th>
            <th>{{ $t('m.Title') }}</th>
            <th class="rule-column">{{ $t('m.Rule') }}</th>
            <th class="action-column"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="problem in libraryProblems" :key="problem.id">
            <td class="id-column">{{ problem._id }}</td>
            <td class="title-column">{{ problem.title }}</td>
            <td class="rule-column">{{ problem.rule_type }}</td>
            <td class="action-column">
              <el-button size="small" :type="added.includes(problem.id) ? 'default' : 'primary'"
                         :disabled="added.includes(problem.id) || problem.rule_type !== ruleType || adding === problem.id"
                         @click="addProblem(problem)">
                {{ added.includes(problem.id) ? $t('m.Prep_Added') : $t('m.Prep_Add') }}
              </el-button>
            </td>
          </tr>
          <tr v-if="!pickerLoading && !libraryProblems.length">
            <td colspan="4" class="prep-empty">{{ $t('m.Prep_No_Problems') }}</td>
          </tr>
        </tbody>
      </table>
      <Pagination v-if="total > limit" :total="total" :page-size="limit" :current="page"
                  @update:current="page = $event" @on-change="loadProblems"></Pagination>
      <template #footer>
        <el-button type="primary" @click="finishPicking">{{ $t('m.Prep_Done') }}</el-button>
      </template>
    </LegacyDialog>
  </section>
</template>

<script>
import api from '@oj/api'
import { mapGetters, mapState } from '@/store/compat'
import { csrfHeaders } from '@/utils/csrf'
import Pagination from '@oj/components/Pagination.vue'
import ProblemEditorForm from '@/shared/problem/ProblemEditorForm.vue'
import { prepProblemService } from './prepProblemService'

export default {
  name: 'ContestPrepUpload',
  components: { Pagination, ProblemEditorForm },
  data () {
    return {
      importing: false,
      remark: '',
      importAction: '/api/contest/prep/import_problem',
      pickerVisible: false,
      pickerLoading: false,
      keyword: '',
      libraryProblems: [],
      total: 0,
      page: 1,
      limit: 10,
      added: [],
      adding: null,
      searchTimer: null,
      generation: 0
    }
  },
  computed: {
    ...mapGetters(['canEditPrep']),
    ...mapState({ ruleType: state => state.contest.contest.rule_type }),
    contestID () {
      return this.$route.params.contestID
    },
    service () {
      return prepProblemService(this.contestID)
    }
  },
  beforeUnmount () {
    clearTimeout(this.searchTimer)
  },
  methods: {
    csrfHeaders,
    async saved (res) {
      // The remark opens the new problem's thread.
      const remark = this.remark.trim()
      const problem = res && res.data && res.data.data
      if (remark && problem) {
        try {
          await api.addPrepFeedback(this.contestID, problem.id, remark)
        } catch (_) {
          // The API client already shows the error; the problem itself is saved.
        }
      }
      this.backToList()
    },
    backToList () {
      this.$router.push({ name: 'contest-prep-problems', params: { contestID: this.contestID } })
    },
    importSucceeded (response) {
      this.importing = false
      if (response.error) {
        this.$error(response.data)
        return
      }
      this.$success(this.$t('m.Prep_Imported', { count: response.data.import_count }))
      this.backToList()
    },
    importFailed () {
      this.importing = false
      this.$error(this.$t('m.Prep_Import_Failed'))
    },
    openPicker () {
      this.pickerVisible = true
      this.page = 1
      this.loadProblems()
    },
    searchProblems () {
      clearTimeout(this.searchTimer)
      this.searchTimer = setTimeout(() => {
        this.page = 1
        this.loadProblems()
      }, 300)
    },
    async loadProblems () {
      const generation = ++this.generation
      this.pickerLoading = true
      try {
        const res = await api.getProblemList((this.page - 1) * this.limit, this.limit, { keyword: this.keyword.trim() })
        if (generation !== this.generation) return
        this.libraryProblems = res.data.data.results
        this.total = res.data.data.total
      } catch (_) {
        // The API client already shows the error.
      } finally {
        if (generation === this.generation) this.pickerLoading = false
      }
    },
    async addProblem (problem) {
      this.adding = problem.id
      try {
        await api.addPrepProblemFromPublic(this.contestID, problem.id)
        this.added.push(problem.id)
      } catch (_) {
        // The API client already shows the error.
      } finally {
        this.adding = null
      }
    },
    finishPicking () {
      this.pickerVisible = false
      if (this.added.length) this.backToList()
    }
  }
}
</script>

<style scoped lang="less">
@import "@/styles/contest-prep.less";

:deep(.section-actions .el-button .legacy-icon) { display: inline-flex; margin-right: 4px; }
.picker-table {
  width: 100%;
  margin-top: 12px;
  border-collapse: collapse;
  font-size: 13px;
  th, td { padding: 9px 10px; border-bottom: 1px solid var(--color-border); text-align: left; }
  th { color: var(--color-text-muted); font-weight: 600; }
}
.remark-heading {
  margin-bottom: 14px;
  h3 { margin: 0; color: var(--color-text); font-size: 16px; font-weight: 680; }
  p { margin: 4px 0 0; color: var(--color-text-muted); font-size: 12px; line-height: 1.55; }
}
.id-column { width: 90px; }
.title-column { color: var(--color-text); }
.rule-column { width: 70px; color: var(--color-text-muted); }
.action-column { width: 90px; text-align: right !important; }
</style>
