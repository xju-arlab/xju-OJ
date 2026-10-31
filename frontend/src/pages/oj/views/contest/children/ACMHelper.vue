<template>
  <panel class="acm-helper-panel" shadow>
    <template #title><div class="helper-title"><Icon type="shield" /><span>{{$t('m.ACM_Helper')}}</span></div></template>
    <template #extra>
      <div class="helper-header-actions">
        <label class="helper-setting">
          <span>{{$t('m.Auto_Refresh')}} (10s)</span>
          <i-switch v-model="autoRefresh" @on-change="handleAutoRefresh"></i-switch>
        </label>
        <button type="button" class="helper-refresh" :disabled="loadingTable" @click="getACInfo(page)">
          <Icon type="refresh" :class="{'is-spinning': loadingTable}" />
          <span>{{$t('m.Refresh')}}</span>
        </button>
      </div>
    </template>
    <Table class="helper-table" :data="pagedAcInfo" :columns="columns" :loading="loadingTable" disabled-hover></Table>
    <pagination :total="total"
                :page-size="limit" @update:page-size="limit = $event"
                :current="page" @update:current="page = $event"
                @on-change="handlePage"
                @on-page-size-change="handlePage(1)"
                show-sizer></pagination>
  </panel>
</template>
<script>
  import { mapState, mapActions } from '@/store/compat'
  import { types } from '../../../../../store'
  import moment from 'moment'
  import Pagination from '@oj/components/Pagination.vue'
  import api from '@oj/api'
  import { cloneFixtures, MOCK_ACM_HELPER } from '@oj/mocks/fixtures'

  export default {
    name: 'acm-helper',
    components: {
      Pagination
    },
    data () {
      return {
        page: 1,
        total: 0,
        loadingTable: false,
        autoRefresh: false,
        usingMockData: false,
        columns: [
          {
            title: this.$t('m.AC_Time'),
            key: 'ac_time'
          },
          {
            title: this.$t('m.ProblemID'),
            align: 'center',
            key: 'problem_display_id'
          },
          {
            title: this.$t('m.First_Blood'),
            align: 'center',
            render: (h, {row}) => {
              if (row.ac_info.is_first_ac) {
                return h('span', {class: 'helper-badge is-first'}, this.$t('m.First_Blood'))
              } else {
                return h('span', {class: 'helper-empty'}, '—')
              }
            }
          },
          {
            title: this.$t('m.Username'),
            align: 'center',
            render: (h, {row}) => {
              return h('button', {
                class: 'helper-user-link',
                on: {
                  click: () => {
                    this.$router.push({
                      name: 'contest-submission-list',
                      query: {username: row.username}
                    })
                  }
                },
                // A team account shows as its team; its real name lists the members.
                title: row.team ? row.username : undefined
              }, row.team || row.username)
            }
          },
          {
            title: this.$t('m.RealName'),
            align: 'center',
            render: (h, {row}) => {
              return h('span', {
                style: {
                  display: 'inline-block',
                  'max-width': '150px'
                }
              }, row.real_name)
            }
          },
          {
            title: this.$t('m.Status'),
            align: 'center',
            render: (h, {row}) => {
              return h('span', {
                class: ['helper-badge', row.checked ? 'is-checked' : 'is-pending']
              }, row.checked ? this.$t('m.Checked') : this.$t('m.Not_Checked'))
            }
          },
          {
            title: this.$t('m.Option'),
            fixed: 'right',
            align: 'center',
            width: 132,
            render: (h, {row}) => {
              return h('button', {
                class: ['helper-check-button', {'is-complete': row.checked}],
                disabled: row.checked,
                on: {
                  click: () => {
                    this.updateCheckedStatus(row)
                  }
                }
              }, [h('Icon', {props: {type: 'check'}}), h('span', row.checked ? this.$t('m.Checked') : this.$t('m.Check_It'))])
            }
          }
        ],
        acInfo: [],
        pagedAcInfo: [],
        problemsMap: {}
      }
    },
    mounted () {
      this.contestID = this.$route.params.contestID
      if (this.contestProblems.length === 0) {
        this.getContestProblems().then((res) => {
          this.mapProblemDisplayID()
          this.getACInfo()
        })
      } else {
        this.mapProblemDisplayID()
        this.getACInfo()
      }
    },
    methods: {
      ...mapActions(['getContestProblems']),
      mapProblemDisplayID () {
        let problemsMap = {}
        this.contestProblems.forEach(ele => {
          problemsMap[ele.id] = ele._id
        })
        this.problemsMap = problemsMap
      },
      getACInfo (page = 1) {
        this.page = Number(page) || 1
        this.loadingTable = true
        let params = {
          contest_id: this.$route.params.contestID
        }
        api.getACMACInfo(params).then(res => {
          this.loadingTable = false
          this.usingMockData = false
          let data = Array.isArray(res.data.data) ? res.data.data : []
          if (!data.length && MOCK_ACM_HELPER.length) {
            this.usingMockData = true
            data = cloneFixtures(MOCK_ACM_HELPER)
          }
          this.total = data.length
          this.acInfo = data
          this.handlePage(this.page)
        }).catch(() => {
          this.loadingTable = false
          this.usingMockData = true
          this.acInfo = cloneFixtures(MOCK_ACM_HELPER)
          this.total = this.acInfo.length
          this.handlePage(this.page)
        })
      },
      updateCheckedStatus (row) {
        if (this.usingMockData) {
          row.checked = true
          row.ac_info.checked = true
          this.$success('Succeeded')
          return
        }
        let data = {
          rank_id: row.id,
          contest_id: this.contestID,
          problem_id: row.problem_id,
          checked: true
        }
        api.updateACInfoCheckedStatus(data).then(res => {
          this.$success('Succeeded')
          this.getACInfo()
        }).catch(() => {
        })
      },
      handleAutoRefresh (value) {
        clearInterval(this.refreshFunc)
        this.autoRefresh = value === true
        if (this.autoRefresh) {
          this.refreshFunc = setInterval(() => {
            this.page = 1
            this.getACInfo()
          }, 10000)
        }
      },
      handlePage (page = 1) {
        this.page = Number(page) || 1
        if (page !== 1) {
          this.loadingTable = true
        }
        let pageInfo = this.acInfo.slice((this.page - 1) * this.limit, this.page * this.limit)
        for (let v of pageInfo) {
          if (v.init) {
            continue
          } else {
            v.init = true
            v.problem_display_id = this.problemsMap[v.problem_id]
            v.ac_time = moment(this.contest.start_time).add(v.ac_info.ac_time, 'seconds').local().format('YYYY-M-D  HH:mm:ss')
          }
        }
        this.pagedAcInfo = pageInfo
        this.loadingTable = false
      }
    },
    computed: {
      ...mapState({
        'contest': state => state.contest.contest,
        'contestProblems': state => state.contest.contestProblems
      }),
      limit: {
        get () {
          return this.$store.state.contest.rankLimit
        },
        set (value) {
          this.$store.commit(types.CHANGE_CONTEST_RANK_LIMIT, {rankLimit: value})
        }
      }
    },
    beforeUnmount () {
      clearInterval(this.refreshFunc)
    }
  }
</script>
<style lang="less" scoped>
  .helper-title { display: inline-flex; align-items: center; gap: 8px; color: var(--color-text); font-size: 15px; font-weight: 650; }
  .helper-title :deep(.legacy-icon) { display: inline-flex; align-items: center; line-height: 0; }
  .acm-helper-panel :deep(.el-card__header) { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
  .acm-helper-panel :deep(.panel-extra) { min-width: 0; flex: 1; }
  .helper-header-actions { display: flex; min-height: 40px; align-items: center; justify-content: flex-end; gap: 14px; padding-right: 1px; line-height: normal; }
  .helper-setting { display: inline-flex; align-items: center; gap: 8px; color: var(--color-text-muted); font-size: 12px; }
  .helper-refresh, :deep(.helper-check-button) { display: inline-flex; min-height: 32px; align-items: center; justify-content: center; gap: 7px; padding: 0 10px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg); color: var(--color-text-muted); font: inherit; font-size: 12px; cursor: pointer; transition: color var(--transition), border-color var(--transition), background-color var(--transition); }
  .helper-refresh:hover, .helper-refresh:focus-visible, :deep(.helper-check-button:hover:not(:disabled)), :deep(.helper-check-button:focus-visible:not(:disabled)) { border-color: var(--line-strong); background: var(--color-bg-subtle); color: var(--color-text); }
  .helper-refresh:disabled, :deep(.helper-check-button:disabled) { cursor: default; opacity: .6; }
  .helper-refresh :deep(.legacy-icon), :deep(.helper-check-button .legacy-icon) { display: inline-flex; align-items: center; line-height: 0; }
  .helper-refresh .is-spinning { animation: helper-spin 900ms linear infinite; }
  :deep(.helper-user-link) { appearance: none; max-width: 150px; overflow: hidden; padding: 0; border: 0; background: transparent; color: var(--color-link); font: inherit; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
  :deep(.helper-user-link:hover), :deep(.helper-user-link:focus-visible) { text-decoration: underline; text-underline-offset: 3px; }
  :deep(.helper-badge) { display: inline-flex; min-width: 66px; min-height: 24px; align-items: center; justify-content: center; padding: 0 8px; border-radius: var(--radius-sm); font-size: 11px; font-weight: 650; line-height: 1; }
  :deep(.helper-badge.is-first) { background: var(--tag-research-bg); color: var(--cat-research); }
  :deep(.helper-badge.is-checked) { background: var(--tag-tools-bg); color: var(--cat-tools); }
  :deep(.helper-badge.is-pending) { background: var(--tag-course-bg); color: var(--cat-course); }
  :deep(.helper-empty) { color: var(--color-text-faint); }
  :deep(.helper-check-button.is-complete) { border-color: transparent; background: var(--tag-tools-bg); color: var(--cat-tools); }
  :deep(.helper-check-button) { font-weight: 650; }
  :deep(.el-table) { --el-table-row-hover-bg-color: var(--color-bg-subtle); border-radius: var(--radius-sm); }
  :deep(.el-table th.el-table__cell) { background: #fcfbf9; color: var(--color-text-muted); font-size: 12px; }
  :deep(.el-table td.el-table__cell) { padding: 9px 0; }

  @keyframes helper-spin { to { transform: rotate(360deg); } }

  @media (max-width: 620px) {
    .helper-header-actions { gap: 8px; }
    .helper-setting > span { display: none; }
  }

  @media (prefers-reduced-motion: reduce) {
    .helper-refresh .is-spinning { animation: none; }
  }
</style>
