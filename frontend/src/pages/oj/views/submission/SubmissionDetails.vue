<template>
  <div class="submission-details-page">
    <section :class="['detail-surface', 'submission-summary', `is-${status.type}`]">
      <div class="summary-status-row">
        <span class="summary-label">{{ $t('m.Status') }}</span>
        <span :class="['judge-status-badge', `is-${status.type}`]">
          {{ status.label }}
        </span>
      </div>

      <RemoteSubmissionNotice :submission="submission" @updated="getSubmission" />

      <pre v-if="isCE" class="compile-error-output">{{submission.statistic_info.err_info || submission.remote_message}}</pre>
      <div v-else class="submission-metrics">
        <div class="submission-metric">
          <span>{{ $t('m.Time') }}</span>
          <strong>{{ $filters.submissionTime(submission.statistic_info.time_cost) }}</strong>
        </div>
        <div class="submission-metric">
          <span>{{ $t('m.Memory') }}</span>
          <strong>{{ $filters.submissionMemory(submission.statistic_info.memory_cost) }}</strong>
        </div>
        <div class="submission-metric">
          <span>{{ $t('m.Lang') }}</span>
          <strong>{{submission.language || '—'}}</strong>
        </div>
        <div class="submission-metric">
          <span>{{ $t('m.Author') }}</span>
          <strong>{{submission.username || '—'}}</strong>
        </div>
      </div>
    </section>

    <!-- 后台返回测试点详情时显示，权限控制仍由后台负责。 -->
    <section v-if="testCaseRows.length && !isCE" class="detail-surface test-case-section">
      <div class="detail-section-header">
        <h2>{{ $t('m.Test_Case_Results') }}</h2>
      </div>
      <Table class="test-case-table"
             :loading="loading"
             :disabled-hover="true"
             :columns="columns"
             :data="testCaseRows"></Table>
    </section>

    <section class="detail-surface source-code-section">
      <div class="detail-section-header code-section-header">
        <div>
          <h2>{{ $t('m.Submitted_Code') }}</h2>
          <span>{{submission.language || '—'}}</span>
        </div>
        <button type="button"
                class="copy-code-button"
                :class="{'is-copied': codeCopied}"
                :disabled="!submission.code"
                @click="copyCode">
          <Icon :type="codeCopied ? 'check' : 'copy'" />
          <span>{{ $t(codeCopied ? 'm.Code_Copied' : 'm.Copy_Code') }}</span>
        </button>
      </div>
      <Highlight :code="submission.code" :language="submission.language"></Highlight>
    </section>

    <div v-if="submission.can_unshare" class="share-row">
      <div id="share-btn">
        <LegacyButton v-if="submission.shared"
                type="warning" size="large" @click="shareSubmission(false)">
          {{$t('m.UnShare')}}
        </LegacyButton>
        <LegacyButton v-else
                type="primary" size="large" @click="shareSubmission(true)">
          {{$t('m.Share')}}
        </LegacyButton>
      </div>
    </div>
  </div>

</template>
<script>
  import api from '@oj/api'
  import {JUDGE_STATUS} from '@/utils/constants'
  import utils from '@/utils/utils'
  import Highlight from '@/pages/oj/components/Highlight'
  import RemoteSubmissionNotice from '@oj/components/RemoteSubmissionNotice.vue'
  import { isSubmissionPending, submissionStatus } from '@oj/submissionStatus'

  export default {
    name: 'submissionDetails',
    components: {
      Highlight, RemoteSubmissionNotice
    },
    data () {
      return {
        columns: [
          {
            title: this.$t('m.ID'),
            align: 'center',
            width: 72,
            render: (h, params) => h('span', String(params.index + 1))
          },
          {
            title: this.$t('m.Status'),
            align: 'center',
            render: (h, params) => {
              const status = JUDGE_STATUS[params.row.result] || JUDGE_STATUS['6']
              return h('span', {
                class: ['judge-status-badge', `is-${status.type || 'info'}`]
              }, this.$t('m.' + status.name.replace(/ /g, '_')))
            }
          },
          {
            title: this.$t('m.Memory'),
            align: 'center',
            render: (h, params) => {
              return h('span', utils.submissionMemoryFormat(params.row.memory))
            }
          },
          {
            title: this.$t('m.Time'),
            align: 'center',
            render: (h, params) => {
              return h('span', utils.submissionTimeFormat(params.row.cpu_time))
            }
          }
        ],
        submission: {
          result: '0',
          code: '',
          info: {
            data: []
          },
          statistic_info: {
            time_cost: '',
            memory_cost: ''
          }
        },
        isConcat: false,
        loading: false,
        codeCopied: false,
        copyResetTimer: null,
        refreshTimer: null,
        disposed: false
      }
    },
    mounted () {
      this.getSubmission()
    },
    methods: {
      getSubmission () {
        if (this.loading || this.disposed) return
        clearTimeout(this.refreshTimer)
        const id = this.$route.params.id
        this.loading = true
        api.getSubmission(id).then(res => {
          this.loading = false
          if (this.disposed) return
          if (id !== this.$route.params.id) { this.getSubmission(); return }
          let data = res.data.data
          if (data.info && Array.isArray(data.info.data) && data.info.data.length && !this.isConcat) {
            // score exist means the submission is OI problem submission
            if (data.info.data[0].score !== undefined) {
              this.isConcat = true
              const scoreColumn = {
                title: this.$t('m.Score'),
                align: 'center',
                key: 'score'
              }
              this.columns.push(scoreColumn)
            }
            if (this.isAdminRole) {
              this.isConcat = true
              const adminColumn = [
                {
                  title: this.$t('m.Real_Time'),
                  align: 'center',
                  render: (h, params) => {
                    return h('span', utils.submissionTimeFormat(params.row.real_time))
                  }
                },
                {
                  title: this.$t('m.Signal'),
                  align: 'center',
                  key: 'signal'
                }
              ]
              this.columns = this.columns.concat(adminColumn)
            }
          }
          this.submission = data
          if (isSubmissionPending(data)) this.refreshTimer = setTimeout(this.getSubmission, 3000)
        }, () => {
          this.loading = false
          if (!this.disposed && id !== this.$route.params.id) { this.getSubmission(); return }
          if (!this.disposed) this.refreshTimer = setTimeout(this.getSubmission, 10000)
        })
      },
      shareSubmission (shared) {
        let data = {id: this.submission.id, shared: shared}
        api.updateSubmission(data).then(res => {
          this.getSubmission()
          this.$success(this.$t('m.Succeeded'))
        }, () => {
        })
      },
      async copyCode () {
        if (!this.submission.code) return
        try {
          try {
            await this.$copyText(this.submission.code)
          } catch (_) {
            this.copyTextFallback(this.submission.code)
          }
          this.codeCopied = true
          this.$success(this.$t('m.Code_Copied'))
          clearTimeout(this.copyResetTimer)
          this.copyResetTimer = setTimeout(() => {
            this.codeCopied = false
          }, 1800)
        } catch (_) {
          this.$error(this.$t('m.Copy_Code_Failed'))
        }
      },
      copyTextFallback (text) {
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.setAttribute('readonly', '')
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        textarea.style.pointerEvents = 'none'
        document.body.appendChild(textarea)
        textarea.select()
        const copied = document.execCommand('copy')
        textarea.remove()
        if (!copied) throw new Error('copy command failed')
      }
    },
    computed: {
      status () {
        return submissionStatus(this.submission, this.$t)
      },
      testCaseRows () {
        return this.submission.info && Array.isArray(this.submission.info.data)
          ? this.submission.info.data
          : []
      },
      isCE () {
        return this.submission.result === -2
      },
      isAdminRole () {
        return this.$store.getters.isAdminRole
      }
    },
    beforeUnmount () {
      this.disposed = true
      clearTimeout(this.refreshTimer)
      clearTimeout(this.copyResetTimer)
    },
    watch: { '$route.params.id' () { this.getSubmission() } }
  }
</script>

<style scoped lang="less">
  .submission-details-page {
    display: grid;
    width: min(100%, 1080px);
    margin: 24px auto 32px;
    gap: 12px;
  }

  .detail-surface {
    overflow: hidden;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-bg);
    box-shadow: none;
  }

  .submission-summary {
    padding: 17px 20px 18px;
  }

  .summary-status-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .summary-label {
    color: var(--color-text-muted);
    font-size: 13px;
    font-weight: 600;
  }

  .judge-status-badge,
  :deep(.test-case-table .judge-status-badge) {
    position: relative;
    display: inline-flex;
    overflow: hidden;
    min-width: 76px;
    height: 24px;
    align-items: center;
    justify-content: center;
    padding: 0 10px;
    border: 0;
    border-radius: var(--radius-pill);
    font-size: 12px;
    font-weight: 650;
    line-height: 1;
    white-space: nowrap;
  }

  .judge-status-badge.is-success,
  :deep(.test-case-table .judge-status-badge.is-success) { --judge-status-bg: var(--tag-tools-bg); background: var(--judge-status-bg); color: var(--cat-tools); }
  .judge-status-badge.is-error,
  :deep(.test-case-table .judge-status-badge.is-error) { --judge-status-bg: var(--tag-research-bg); background: var(--judge-status-bg); color: var(--cat-research); }
  .judge-status-badge.is-warning,
  :deep(.test-case-table .judge-status-badge.is-warning) { --judge-status-bg: var(--tag-course-bg); background: var(--judge-status-bg); color: var(--cat-course); }
  .judge-status-badge.is-info,
  :deep(.test-case-table .judge-status-badge.is-info) { --judge-status-bg: var(--tag-kaggle-bg); background: var(--judge-status-bg); color: var(--cat-kaggle); }
  .judge-status-badge:not(.is-success),
  :deep(.test-case-table .judge-status-badge:not(.is-success)) {
    background-image:
      linear-gradient(108deg, transparent 28%, rgba(255, 255, 255, .72) 46%, transparent 64%),
      linear-gradient(var(--judge-status-bg), var(--judge-status-bg));
    background-position: 170% 0, 0 0;
    background-size: 190% 100%, 100% 100%;
    animation:
      judge-status-shimmer 1.65s linear infinite,
      judge-status-heartbeat 2.2s ease-in-out infinite;
  }

  @keyframes judge-status-shimmer {
    from { background-position: 170% 0, 0 0; }
    to { background-position: -90% 0, 0 0; }
  }

  @keyframes judge-status-heartbeat {
    0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 0%, transparent); }
    45% { box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 8%, transparent); }
    55% { box-shadow: 0 0 0 1px color-mix(in srgb, currentColor 4%, transparent); }
  }

  .submission-metrics {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    margin-top: 15px;
    padding-top: 15px;
    border-top: 1px solid var(--color-border);
    gap: 12px 18px;
  }

  .submission-metric {
    display: flex;
    min-width: 0;
    flex-direction: column;
    gap: 4px;
    span { color: var(--color-text-faint); font-size: 12px; }
    strong { overflow: hidden; color: var(--color-text); text-overflow: ellipsis; white-space: nowrap; font-size: 14px; font-weight: 600; }
  }

  .compile-error-output {
    margin: 14px 0 0;
    padding: 14px 16px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg-subtle);
    color: var(--color-text);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .detail-section-header {
    display: flex;
    min-height: 52px;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--color-border);
    background: var(--color-bg);
    h2 { margin: 0; color: var(--color-text); font-size: 15px; font-weight: 650; }
  }

  .test-case-section {
    margin-top: -2px;
  }

  :deep(.test-case-table) {
    .el-table__inner-wrapper::before { display: none; }
    .el-table__header th.el-table__cell { padding: 9px 0; background: var(--color-bg-subtle); color: var(--color-text-muted); font-weight: 600; }
    .el-table__body td.el-table__cell { padding: 9px 0; border-bottom-color: var(--color-border); }
    .cell { padding: 0 10px; }
    .judge-status-badge { vertical-align: middle; }
  }

  .code-section-header > div {
    display: flex;
    align-items: baseline;
    gap: 10px;
    > span { color: var(--color-text-faint); font-size: 12px; }
  }

  .copy-code-button {
    appearance: none;
    display: inline-flex;
    height: 32px;
    align-items: center;
    justify-content: center;
    gap: 7px;
    padding: 0 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg);
    color: var(--color-text-muted);
    cursor: pointer;
    font-size: 12px;
    transition: color var(--transition), border-color var(--transition), background-color var(--transition);
    &:hover:not(:disabled), &:focus-visible { border-color: var(--line-strong); background: var(--color-bg-subtle); color: var(--color-text); }
    &.is-copied { border-color: #b9dfc6; background: var(--tag-tools-bg); color: var(--cat-tools); }
    &:disabled { cursor: not-allowed; opacity: .48; }
    :deep(.legacy-icon) { display: inline-flex; }
  }

  .source-code-section :deep(.highlight-shell) {
    border: 0;
    border-radius: 0;
  }

  .share-row {
    display: flex;
    justify-content: flex-end;
    padding-top: 2px;
  }

  #share-btn {
    display: flex;
    justify-content: flex-end;
  }

  @media (max-width: 760px) {
    .submission-details-page { margin-top: 12px; gap: 10px; }
    .submission-summary { padding: 15px 14px; }
    .submission-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .detail-section-header { padding: 11px 13px; }
    .copy-code-button span { display: none; }
    .copy-code-button { width: 32px; padding: 0; }
  }
</style>
