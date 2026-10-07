<template>
  <div v-if="pending" class="remote-submission-notice" role="status">
    <span>{{syncMessage || presentation.hint}}</span>
    <button v-if="isOwner" type="button" :disabled="recovering" @click="recover">
      {{$t(submission.remote_submission_id ? 'm.Remote_Sync_Result' : 'm.Remote_Continue_Submission')}}
    </button>
  </div>
</template>

<script>
  import api from '@oj/api'
  import { dispatchRemoteSubmission, isRemoteBridgeInstalled, subscribeRemoteBridgeEvents } from '@oj/remoteBridge'
  import { isSubmissionPending, submissionStatus } from '@oj/submissionStatus'

  export default {
    props: { submission: { type: Object, required: true } },
    emits: ['updated'],
    data: () => ({ recovering: false, syncMessage: '', unsubscribe: null }),
    computed: {
      pending () { return this.submission.judge_mode === 'REMOTE' && isSubmissionPending(this.submission) },
      isOwner () { return String(this.submission.user_id) === String(this.$store.getters.user.id) },
      presentation () { return submissionStatus(this.submission, this.$t) }
    },
    mounted () {
      this.unsubscribe = subscribeRemoteBridgeEvents(event => {
        if (event.submission_id !== this.submission.id) return
        this.syncMessage = event.status === 'SYNC_PENDING' ? event.message : ''
        this.$emit('updated')
      })
    },
    beforeUnmount () { if (this.unsubscribe) this.unsubscribe() },
    methods: {
      async recover () {
        if (!isRemoteBridgeInstalled()) {
          this.$Modal.info({
            title: this.$t('m.Remote_Bridge_Required_Title'),
            content: this.$t('m.Remote_Update_Helper'),
            onOk: () => window.open('/remote-bridge', '_blank', 'noopener,noreferrer')
          })
          return
        }
        this.recovering = true
        try {
          const response = await api.recoverRemoteSubmission(this.submission.id)
          const { task, code } = response.data.data
          if (task) dispatchRemoteSubmission(task, code)
          this.$emit('updated')
        } catch (error) {
          this.$error(error.message || this.$t('m.Remote_Recovery_Failed'))
        } finally { this.recovering = false }
      }
    }
  }
</script>

<style scoped>
  .remote-submission-notice { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 12px; padding: 12px; background: var(--color-bg-subtle); border-radius: var(--radius-sm); color: var(--color-text-muted); }
  button { padding: 6px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg); color: var(--color-text); cursor: pointer; }
  button:disabled { opacity: .5; cursor: wait; }
</style>
