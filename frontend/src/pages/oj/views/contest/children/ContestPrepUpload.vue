<template>
  <section class="prep-panel" :aria-label="$t('m.Prep_Upload')">
    <p v-if="!canEditPrep" class="prep-empty">{{ $t('m.Prep_Problem_Locked') }}</p>
    <template v-else>
      <div class="prep-upload-bar">
        <el-upload :action="importAction"
                   :headers="csrfHeaders()"
                   :data="{ contest_id: contestID }"
                   name="file"
                   accept=".zip"
                   :show-file-list="false"
                   :before-upload="() => { importing = true; return true }"
                   :on-success="importSucceeded"
                   :on-error="importFailed">
          <el-button :loading="importing"><Icon type="upload" />{{ $t('m.Prep_Import_Zip') }}</el-button>
        </el-upload>
      </div>
      <ProblemEditorForm mode="add"
                         :contest-id="contestID"
                         :service="service"
                         @saved="backToList" />
    </template>
  </section>
</template>

<script>
import api from '@oj/api'
import { mapGetters } from '@/store/compat'
import { csrfHeaders } from '@/utils/csrf'
import ProblemEditorForm from '@/shared/problem/ProblemEditorForm.vue'
import { prepProblemService } from './prepProblemService'

export default {
  name: 'ContestPrepUpload',
  components: { ProblemEditorForm },
  data () {
    return {
      importing: false,
      importAction: '/api/contest/prep/import_problem'
    }
  },
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
    csrfHeaders,
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
    }
  }
}
</script>

<style scoped lang="less">
@import "@/styles/contest-prep.less";

.prep-upload-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 14px;
  :deep(.legacy-icon) { display: inline-flex; margin-right: 4px; }
}
</style>
