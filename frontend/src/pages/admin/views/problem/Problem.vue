<template>
  <div class="problem">
    <Panel :title="title">
      <ProblemEditorForm :mode="mode"
                         :problem-id="$route.params.problemId"
                         :contest-id="$route.params.contestId"
                         :service="service"
                         @saved="onSaved" />
    </Panel>
  </div>
</template>
<script>
  import ProblemEditorForm from '@/shared/problem/ProblemEditorForm.vue'
  import api from '../../api'

  const unwrap = res => res.data.data

  export default {
    name: 'Problem',
    components: {
      ProblemEditorForm
    },
    computed: {
      isContestProblem () {
        return Boolean(this.$route.params.contestId)
      },
      mode () {
        return ['edit-problem', 'edit-contest-problem'].includes(this.$route.name) ? 'edit' : 'add'
      },
      title () {
        return this.$t(this.mode === 'edit' ? 'm.Edit_Problem' : 'm.Add_Problem')
      },
      service () {
        const contest = this.isContestProblem
        return {
          getLanguages: () => api.getLanguages().then(unwrap),
          getProblemTagList: params => api.getProblemTagList(params).then(unwrap),
          getContest: id => api.getContest(id).then(unwrap),
          getProblem: id => (contest ? api.getContestProblem(id) : api.getProblem(id)).then(unwrap),
          compileSPJ: data => api.compileSPJ(data),
          saveProblem: (problem, mode) => {
            const action = mode === 'edit' ? 'edit' : 'create'
            return api[`${action}${contest ? 'ContestProblem' : 'Problem'}`](problem)
          },
          testCaseUploadAction: '/api/admin/test_case',
          testCaseUploadData: {}
        }
      }
    },
    methods: {
      onSaved () {
        if (this.isContestProblem) {
          this.$router.push({name: 'contest-problem-list', params: {contestId: this.$route.params.contestId}})
        } else {
          this.$router.push({name: 'problem-list'})
        }
      }
    }
  }
</script>
