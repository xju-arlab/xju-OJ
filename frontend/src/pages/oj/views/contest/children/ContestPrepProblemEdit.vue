<template>
  <section class="prep-panel" :aria-label="$t('m.Edit_Problem')">
    <!-- Every member may write problems; wait for the contest so the role is known. -->
    <ProblemEditorForm v-if="canEditPrep"
                       :key="$route.fullPath"
                       mode="edit"
                       :problem-id="$route.params.problemId"
                       :contest-id="contestID"
                       :service="service"
                       cancelable
                       @saved="backToList"
                       @cancel="backToList">
      <template #remarks>
        <PrepFeedbackThread :contest-id="contestID" :problem-id="$route.params.problemId" />
      </template>
    </ProblemEditorForm>
  </section>
</template>

<script>
import { mapGetters } from '@/store/compat'
import ProblemEditorForm from '@/shared/problem/ProblemEditorForm.vue'
import { prepProblemService } from './prepProblemService'
import PrepFeedbackThread from './PrepFeedbackThread.vue'

export default {
  name: 'ContestPrepProblemEdit',
  components: { ProblemEditorForm, PrepFeedbackThread },
  computed: {
    ...mapGetters(['canEditPrep']),
    contestID () {
      return this.$route.params.contestID
    },
    service () {
      return prepProblemService(this.contestID)
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
:deep(.thread-head) { font-size: 16px; }
:deep(.thread-head strong) { font-weight: 680; }
</style>
