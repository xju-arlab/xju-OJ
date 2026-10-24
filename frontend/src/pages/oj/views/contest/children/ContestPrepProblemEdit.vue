<template>
  <section class="prep-panel" aria-labelledby="prep-problem-edit-title">
    <header class="prep-panel-heading">
      <div>
        <h2 id="prep-problem-edit-title">{{ $t(mode === 'edit' ? 'm.Edit_Problem' : 'm.Add_Problem') }}</h2>
        <p>{{ $t('m.Prep_Problem_Editor_Intro') }}</p>
      </div>
    </header>
    <p v-if="!canEditPrep" class="prep-empty">{{ $t('m.Prep_Problem_Locked') }}</p>
    <ProblemEditorForm v-else
                       :key="$route.fullPath"
                       :mode="mode"
                       :problem-id="$route.params.problemId"
                       :contest-id="contestID"
                       :service="service"
                       cancelable
                       @saved="backToList"
                       @cancel="backToList" />
  </section>
</template>

<script>
import api from '@oj/api'
import { mapGetters } from '@/store/compat'
import ProblemEditorForm from '@/shared/problem/ProblemEditorForm.vue'

const unwrap = res => res.data.data

export default {
  name: 'ContestPrepProblemEdit',
  components: { ProblemEditorForm },
  computed: {
    ...mapGetters(['canEditPrep']),
    contestID () {
      return this.$route.params.contestID
    },
    mode () {
      return this.$route.name === 'contest-prep-problem-edit' ? 'edit' : 'add'
    },
    service () {
      const contestID = this.contestID
      return {
        getLanguages: () => api.getLanguages().then(unwrap),
        getProblemTagList: params => api.getProblemTagList(params).then(unwrap),
        // The contest detail payload carries rule_type and prep_state.
        getContest: () => api.getContest(contestID).then(unwrap),
        getProblem: id => api.getPrepProblem(contestID, id).then(unwrap),
        compileSPJ: data => api.compilePrepSPJ({ ...data, contest_id: contestID }),
        saveProblem: (problem, mode) => {
          const payload = { ...problem, contest_id: contestID }
          return mode === 'edit' ? api.editPrepProblem(payload) : api.createPrepProblem(payload)
        },
        testCaseUploadAction: '/api/contest/prep/test_case',
        testCaseUploadData: { contest_id: contestID }
      }
    }
  },
  methods: {
    backToList () {
      this.$router.push({ name: 'contest-prep-problems', params: { contestID: this.contestID } })
    }
  }
}
</script>

<style scoped lang="less">
@import "@/styles/contest-prep.less";
</style>
