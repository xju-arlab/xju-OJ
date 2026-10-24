<template>
  <section class="prep-panel" :aria-label="$t('m.Edit_Problem')">
    <p v-if="!canEditPrep" class="prep-empty">{{ $t('m.Prep_Problem_Locked') }}</p>
    <ProblemEditorForm v-else
                       :key="$route.fullPath"
                       mode="edit"
                       :problem-id="$route.params.problemId"
                       :contest-id="contestID"
                       :service="service"
                       cancelable
                       @saved="backToList"
                       @cancel="backToList" />
  </section>
</template>

<script>
import { mapGetters } from '@/store/compat'
import ProblemEditorForm from '@/shared/problem/ProblemEditorForm.vue'
import { prepProblemService } from './prepProblemService'

export default {
  name: 'ContestPrepProblemEdit',
  components: { ProblemEditorForm },
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
</style>
