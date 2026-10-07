<template>
  <div class="flex-container">
    <div id="main">
      <Panel shadow>
        <template #title><div >{{title}}</div></template>
        <template #extra><div class="submission-filters">
          <Dropdown @on-click="handleResultChange">
            <button type="button" class="filter-control status-filter">
              <span>{{status}}</span>
              <Icon type="arrow-down-b"></Icon>
            </button>
            <template #list><Dropdown-menu>
              <Dropdown-item name="">{{$t('m.All')}}</Dropdown-item>
              <Dropdown-item v-for="status in Object.keys(JUDGE_STATUS)" :key="status" :name="status">
                {{$t('m.' + JUDGE_STATUS[status].name.replace(/ /g, "_"))}}
              </Dropdown-item>
            </Dropdown-menu></template>
          </Dropdown>
          <button type="button" class="filter-control mine-toggle" :class="{'is-active': formFilter.myself}"
                  :aria-pressed="formFilter.myself" @click="formFilter.myself = !formFilter.myself; handleQueryChange()">
            <Icon type="user"></Icon>
            <span>{{formFilter.myself ? $t('m.Mine') : $t('m.All')}}</span>
          </button>
          <Input v-model="formFilter.username" class="keyword-filter" :placeholder="$t('m.Search_Author')" @on-enter="handleQueryChange"/>
          <button type="button" class="filter-control reset-filter" @click="onReset">
            <Icon type="refresh"></Icon>
            <span>{{$t('m.Reset')}}</span>
          </button>
          <button type="button" class="filter-control refresh-control" :aria-label="$t('m.Refresh')" :title="$t('m.Refresh')" @click="getSubmissions">
            <Icon type="refresh"></Icon>
          </button>
        </div></template>
        <Table class="submission-table" stripe :disabled-hover="true" :columns="columns" :data="submissions" :loading="loadingTable"></Table>
        <Pagination :total="total" :page-size="limit" @on-change="changeRoute" :current="page" @update:current="page = $event"></Pagination>
      </Panel>
    </div>
  </div>
</template>
<script>
  import { mapGetters } from '@/store/compat'
  import api from '@oj/api'
  import { JUDGE_STATUS, USER_TYPE } from '@/utils/constants'
  import utils from '@/utils/utils'
  import time from '@/utils/time'
  import Pagination from '@/pages/oj/components/Pagination'
  import { submissionStatus } from '@oj/submissionStatus'

  const DISPLAY_JUDGE_STATUS = Object.keys(JUDGE_STATUS).reduce((result, status) => {
    if (status !== '9' && status !== '2') result[status] = JUDGE_STATUS[status]
    return result
  }, {})

  export default {
    name: 'submissionList',
    components: {
      Pagination
    },
    data () {
      return {
        formFilter: {
          myself: false,
          result: '',
          username: ''
        },
        columns: [
          {
            title: this.$t('m.When'),
            width: 152,
            align: 'center',
            render: (h, params) => {
              return h('span', time.utcToLocal(params.row.create_time))
            }
          },
          {
            title: this.$t('m.ID'),
            width: 126,
            align: 'center',
            render: (h, params) => {
              if (params.row.show_link) {
                return h('span', {
                  style: {
                    color: '#57a3f3',
                    cursor: 'pointer'
                  },
                  on: {
                    click: () => {
                      this.$router.push('/status/' + params.row.id)
                    }
                  }
                }, params.row.id.slice(0, 12))
              } else {
                return h('span', params.row.id.slice(0, 12))
              }
            }
          },
          {
            title: this.$t('m.Status'),
            width: 132,
            align: 'center',
            render: (h, params) => {
              const status = submissionStatus(params.row, this.$t)
              return h('span', { title: status.hint, class: ['judge-status-badge', `is-${status.type}`] }, status.label)
            }
          },
          {
            title: this.$t('m.Problem'),
            width: 92,
            align: 'center',
            render: (h, params) => {
              return h('span',
                {
                  style: {
                    color: '#57a3f3',
                    cursor: 'pointer'
                  },
                  on: {
                    click: () => {
                      if (this.contestID) {
                        this.$router.push(
                          {
                            name: 'contest-problem-details',
                            params: {problemID: params.row.problem, contestID: this.contestID}
                          })
                      } else {
                        this.$router.push({name: 'problem-details', params: {problemID: params.row.problem}})
                      }
                    }
                  }
                },
                params.row.problem)
            }
          },
          {
            title: this.$t('m.Time'),
            width: 88,
            align: 'center',
            render: (h, params) => {
              return h('span', utils.submissionTimeFormat(params.row.statistic_info.time_cost))
            }
          },
          {
            title: this.$t('m.Memory'),
            width: 98,
            align: 'center',
            render: (h, params) => {
              return h('span', utils.submissionMemoryFormat(params.row.statistic_info.memory_cost))
            }
          },
          {
            title: this.$t('m.Language'),
            width: 106,
            align: 'center',
            key: 'language'
          },
          {
            title: this.$t('m.Author'),
            width: 116,
            align: 'center',
            render: (h, params) => {
              return h('a', {
                style: {
                  'display': 'inline-block',
                  'max-width': '150px'
                },
                on: {
                  click: () => {
                    this.$router.push(
                      {
                        name: 'user-home',
                        query: {username: params.row.username}
                      })
                  }
                }
              }, params.row.username)
            }
          }
        ],
        loadingTable: false,
        submissions: [],
        total: 30,
        limit: 12,
        page: 1,
        contestID: '',
        problemID: '',
        routeName: '',
        JUDGE_STATUS: DISPLAY_JUDGE_STATUS,
        rejudge_column: false,
        refreshTimer: null,
        requestInFlight: false,
        requestGeneration: 0,
        disposed: false
      }
    },
    mounted () {
      this.init()
    },
    beforeUnmount () {
      this.disposed = true
      this.requestGeneration += 1
      this.clearStatusRefresh()
    },
    methods: {
      init () {
        this.contestID = this.$route.params.contestID
        let query = this.$route.query
        this.problemID = query.problemID
        this.formFilter.myself = query.myself === '1'
        this.formFilter.result = query.result || ''
        this.formFilter.username = query.username || ''
        this.page = parseInt(query.page) || 1
        if (this.page < 1) {
          this.page = 1
        }
        this.routeName = this.$route.name
        this.getSubmissions()
      },
      buildQuery () {
        return {
          myself: this.formFilter.myself === true ? '1' : '0',
          result: this.formFilter.result,
          username: this.formFilter.username,
          page: this.page
        }
      },
      clearStatusRefresh () {
        if (this.refreshTimer) {
          clearTimeout(this.refreshTimer)
          this.refreshTimer = null
        }
      },
      scheduleStatusRefresh (results) {
        this.clearStatusRefresh()
        const hasPending = results.some(item => ['6', '7', '9'].includes(String(item.result)))
        if (!hasPending || document.visibilityState === 'hidden') return
        this.refreshTimer = setTimeout(() => this.getSubmissions({ silent: true }), 2200)
      },
      getSubmissions ({ silent = false } = {}) {
        if (this.disposed || (silent && this.requestInFlight)) return
        const generation = ++this.requestGeneration
        this.clearStatusRefresh()
        let params = this.buildQuery()
        params.contest_id = this.contestID
        params.problem_id = this.problemID
        let offset = (this.page - 1) * this.limit
        let func = this.contestID ? 'getContestSubmissionList' : 'getSubmissionList'
        this.requestInFlight = true
        if (!silent) this.loadingTable = true
        api[func](offset, this.limit, params).then(res => {
          if (this.disposed || generation !== this.requestGeneration) return
          let data = res.data.data
          for (let v of data.results) {
            v.loading = false
          }
          this.adjustRejudgeColumn()
          this.loadingTable = false
          this.submissions = data.results
          this.total = data.total
          this.scheduleStatusRefresh(data.results)
        }).catch(() => {
          if (this.disposed || generation !== this.requestGeneration) return
          this.loadingTable = false
          this.clearStatusRefresh()
        }).finally(() => { if (generation === this.requestGeneration) this.requestInFlight = false })
      },
      // 改变route， 通过监听route变化请求数据，这样可以产生route history， 用户返回时就会保存之前的状态
      changeRoute () {
        let query = utils.filterEmptyValue(this.buildQuery())
        query.contestID = this.contestID
        query.problemID = this.problemID
        let routeName = query.contestID ? 'contest-submission-list' : 'submission-list'
        this.$router.push({
          name: routeName,
          query: utils.filterEmptyValue(query)
        })
      },
      goRoute (route) {
        this.$router.push(route)
      },
      adjustRejudgeColumn () {
        if (!this.rejudgeColumnVisible || this.rejudge_column) {
          return
        }
        const judgeColumn = {
          title: this.$t('m.Option'),
          fixed: 'right',
          align: 'center',
          width: 90,
          render: (h, params) => {
            if (params.row.judge_mode === 'REMOTE') return null
            return h('Button', {
              props: {
                type: 'primary',
                size: 'small',
                loading: params.row.loading
              },
              on: {
                click: () => {
                  this.handleRejudge(params.row.id, params.index)
                }
              }
            }, this.$t('m.Rejudge'))
          }
        }
        this.columns.push(judgeColumn)
        this.rejudge_column = true
      },
      handleResultChange (status) {
        this.page = 1
        this.formFilter.result = status
        this.changeRoute()
      },
      handleQueryChange () {
        this.page = 1
        this.changeRoute()
      },
      onReset () {
        this.formFilter.myself = false
        this.formFilter.result = ''
        this.formFilter.username = ''
        this.page = 1
        this.changeRoute()
      },
      handleRejudge (id, index) {
        this.submissions[index].loading = true
        api.submissionRejudge(id).then(res => {
          this.submissions[index].loading = false
          this.$success('Succeeded')
          this.getSubmissions()
        }, () => {
          this.submissions[index].loading = false
        })
      }
    },
    computed: {
      ...mapGetters(['isAuthenticated', 'user']),
      title () {
        if (!this.contestID) {
          return this.$t('m.Status')
        } else if (this.problemID) {
          return this.$t('m.Problem_Submissions')
        } else {
          return this.$t('m.Submissions')
        }
      },
      status () {
        return this.formFilter.result === '' ? this.$t('m.Status') : this.$t('m.' + JUDGE_STATUS[this.formFilter.result].name.replace(/ /g, '_'))
      },
      rejudgeColumnVisible () {
        return !this.contestID && this.user.admin_type === USER_TYPE.SUPER_ADMIN
      }
    },
    watch: {
      '$route' (newVal, oldVal) {
        if (newVal !== oldVal) {
          this.clearStatusRefresh()
          this.init()
        }
      },
      'rejudgeColumnVisible' () {
        this.adjustRejudgeColumn()
      },
      'isAuthenticated' () {
        this.init()
      }
    }
  }
</script>

<style scoped lang="less">
  .flex-container {
    #main {
      flex: auto;
      margin-right: 18px;
      :deep(.el-card__header) { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
      :deep(.panel-title) { flex: none; }
      :deep(.panel-extra) { min-width: 0; flex: 1; line-height: normal; }
      .submission-filters { display: flex; align-items: center; justify-content: flex-end; gap: 10px; min-height: 34px; white-space: nowrap; }
      .filter-control { appearance: none; display: inline-flex; height: 34px; align-items: center; justify-content: center; gap: 7px; min-width: 104px; padding: 0 11px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg); color: var(--color-text-muted); cursor: pointer; transition: color var(--transition), border-color var(--transition), background-color var(--transition); }
      .filter-control:hover, .filter-control:focus-visible { border-color: var(--line-strong); background: var(--color-bg-subtle); color: var(--color-text); }
      .filter-control.is-active { border-color: color-mix(in srgb, var(--cat-kaggle) 28%, var(--color-border)); background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
      .status-filter { justify-content: space-between; }
      .keyword-filter { width: 210px; }
      .reset-filter { color: var(--color-text); background: var(--color-bg-subtle); }
      .reset-filter:hover { background: var(--bg-hover); }
      .refresh-control { min-width: 34px; width: 34px; padding: 0; }
      :deep(.legacy-icon) { display: inline-flex; }
      :deep(.submission-table .el-table__cell) { padding: 8px 0; }
      :deep(.submission-table .cell) { padding: 0 7px; white-space: nowrap; }
      :deep(.judge-status-badge) { position: relative; display: inline-flex; overflow: hidden; min-width: 76px; height: 24px; align-items: center; justify-content: center; padding: 0 9px; border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; line-height: 1; }
      :deep(.judge-status-badge.is-success) { --judge-status-bg: var(--tag-tools-bg); color: var(--cat-tools); background: var(--judge-status-bg); }
      :deep(.judge-status-badge.is-error) { --judge-status-bg: var(--tag-research-bg); color: var(--cat-research); background: var(--judge-status-bg); }
      :deep(.judge-status-badge.is-warning) { --judge-status-bg: var(--tag-course-bg); color: var(--cat-course); background: var(--judge-status-bg); }
      :deep(.judge-status-badge.is-info) { --judge-status-bg: var(--tag-kaggle-bg); color: var(--cat-kaggle); background: var(--judge-status-bg); }
      :deep(.judge-status-badge:not(.is-success)) {
        background-image:
          linear-gradient(108deg, transparent 28%, rgba(255, 255, 255, .72) 46%, transparent 64%),
          linear-gradient(var(--judge-status-bg), var(--judge-status-bg));
        background-position: 170% 0, 0 0;
        background-size: 190% 100%, 100% 100%;
        animation:
          judge-status-shimmer 1.65s linear infinite,
          judge-status-heartbeat 2.2s ease-in-out infinite;
      }
    }
    #contest-menu {
      flex: none;
      width: 210px;
    }
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
  @media (max-width: 1100px) {
    .flex-container #main {
      :deep(.el-card__header) { align-items: flex-start; flex-direction: column; }
      :deep(.panel-extra) { width: 100%; }
      .submission-filters { justify-content: flex-start; flex-wrap: wrap; }
    }
  }
  @media (max-width: 560px) {
    .flex-container #main {
      .keyword-filter { order: 5; width: 100%; }
    }
  }
</style>
