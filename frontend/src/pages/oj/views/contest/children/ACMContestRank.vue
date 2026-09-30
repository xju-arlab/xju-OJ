<template>
  <Panel shadow>
    <template #title><div class="rank-title">{{ contest.title }}</div></template>
    <div class="rank-settings-row" aria-label="Ranking settings">
      <label class="rank-setting"><span>{{$t('m.Chart')}}</span><i-switch v-model="showChart"></i-switch></label>
      <label class="rank-setting"><span>{{$t('m.Auto_Refresh')}} (10s)</span><i-switch v-model="autoRefresh" :disabled="refreshDisabled" @on-change="handleAutoRefresh"></i-switch></label>
      <template v-if="isContestAdmin">
        <label class="rank-setting"><span>{{$t('m.RealName')}}</span><i-switch v-model="showRealName"></i-switch></label>
        <label class="rank-setting"><span>{{$t('m.Force_Update')}}</span><i-switch v-model="forceUpdate" :disabled="refreshDisabled"></i-switch></label>
      </template>
      <button type="button" class="rank-download" @click="downloadRankCSV">
        <Icon type="download" />
        <span>{{$t('m.download_csv')}}</span>
      </button>
    </div>
    <div v-if="showChart" class="echarts">
      <ECharts :options="options" ref="chart" auto-resize></ECharts>
    </div>
    <Table ref="tableRank" class="auto-resize" :columns="columns" :data="dataRank" disabled-hover></Table>
    <Pagination :total="total"
                :page-size="limit" @update:page-size="limit = $event"
                :current="page" @update:current="page = $event"
                @on-change="getContestRankData"
                @on-page-size-change="getContestRankData(1)"
                show-sizer></Pagination>
  </Panel>
</template>
<script>
  import moment from 'moment'
  import { mapActions } from '@/store/compat'

  import Pagination from '@oj/components/Pagination'
  import ContestRankMixin from './contestRankMixin'
  import utils from '@/utils/utils'

  export default {
    name: 'acm-contest-rank',
    components: {
      Pagination
    },
    mixins: [ContestRankMixin],
    data () {
      return {
        total: 0,
        page: 1,
        contestID: '',
        columns: [
          {
            className: 'rank-hover-cell',
            align: 'center',
            width: 50,
            fixed: 'left',
            render: (h, params) => {
              return h('span', {}, params.index + (this.page - 1) * this.limit + 1)
            }
          },
          {
            className: 'rank-hover-cell',
            title: this.$t('m.User_User'),
            align: 'center',
            fixed: 'left',
            width: 150,
            render: (h, params) => {
              return h('a', {
                style: {
                  display: 'inline-block',
                  'max-width': '150px'
                },
                on: {
                  click: () => {
                    this.$router.push(
                      {
                        name: 'user-home',
                        query: {username: params.row.user.username}
                      })
                  }
                }
              }, params.row.user.username)
            }
          },
          {
            className: 'rank-hover-cell',
            title: 'AC / ' + this.$t('m.Total'),
            align: 'center',
            width: 100,
            render: (h, params) => {
              return h('span', {}, [
                h('span', {}, params.row.accepted_number + ' / '),
                h('a', {
                  on: {
                    click: () => {
                      this.$router.push({
                        name: 'contest-submission-list',
                        query: {username: params.row.user.username}
                      })
                    }
                  }
                }, params.row.submission_number)
              ])
            }
          },
          {
            className: 'rank-hover-cell',
            title: this.$t('m.TotalTime'),
            align: 'center',
            width: 100,
            render: (h, params) => {
              return h('span', this.parseTotalTime(params.row.total_time))
            }
          }
        ],
        dataRank: [],
        options: {
          color: ['#2383e2', '#0f7b6c', '#7c5c9e', '#d9730d', '#4d646f'],
          title: {
            text: this.$t('m.Top_10_Teams'),
            left: 'center'
          },
          dataZoom: [
            {
              type: 'inside',
              filterMode: 'none',
              xAxisIndex: [0],
              start: 0,
              end: 100
            }
          ],
          toolbox: {
            show: true,
            feature: {
              saveAsImage: {show: true, title: this.$t('m.save_as_image')}
            },
            right: '5%'
          },
          tooltip: {
            trigger: 'axis',
            axisPointer: {
              type: 'cross',
              axis: 'x'
            }
          },
          legend: {
            orient: 'vertical',
            y: 'center',
            right: 0,
            data: [],
            formatter: (value) => {
              return utils.breakLongWords(value, 16)
            },
            textStyle: {
              color: '#787774',
              fontSize: 12
            }
          },
          grid: {
            x: 80,
            x2: 200
          },
          xAxis: [{
            type: 'time',
            splitLine: false,
            axisLine: {lineStyle: {color: '#d9d8d4'}},
            axisLabel: {color: '#787774'},
            axisPointer: {
              show: true,
              snap: true
            }
          }],
          yAxis: [
            {
              type: 'category',
              boundaryGap: false,
              data: [0],
              axisLine: {lineStyle: {color: '#d9d8d4'}},
              axisLabel: {color: '#787774'}
            }],
          series: []
        }
      }
    },
    mounted () {
      this.contestID = this.$route.params.contestID
      this.getContestRankData(1)
      if (this.contestProblems.length === 0) {
        this.getContestProblems().then((res) => {
          this.addTableColumns(res.data.data)
          this.addChartCategory(res.data.data)
        })
      } else {
        this.addTableColumns(this.contestProblems)
        this.addChartCategory(this.contestProblems)
      }
    },
    methods: {
      ...mapActions(['getContestProblems']),
      addChartCategory (contestProblems) {
        let category = []
        for (let i = 0; i <= contestProblems.length; ++i) {
          category.push(i)
        }
        this.options.yAxis[0].data = category
      },
      applyToChart (rankData) {
        let [users, seriesData] = [[], []]
        rankData.forEach(rank => {
          users.push(rank.user.username)
          let info = rank.submission_info
          // 提取出已AC题目的时间
          let timeData = []
          Object.keys(info).forEach(problemID => {
            if (info[problemID].is_ac) {
              timeData.push(info[problemID].ac_time)
            }
          })
          timeData.sort((a, b) => {
            return a - b
          })

          let data = []
          data.push([this.contest.start_time, 0])
          // index here can be regarded as stacked accepted number count.
          for (let [index, value] of timeData.entries()) {
            let realTime = moment(this.contest.start_time).add(value, 'seconds').format()
            data.push([realTime, index + 1])
          }
          seriesData.push({
            name: rank.user.username,
            type: 'line',
            data
          })
        })
        this.options.legend.data = users
        this.options.series = seriesData
      },
      applyToTable (data) {
        // deepcopy
        let dataRank = JSON.parse(JSON.stringify(data))
        // 从submission_info中取出相应的problem_id 放入到父object中,这么做主要是为了适应iview table的data格式
        // 见https://www.iviewui.com/components/table
        dataRank.forEach((rank, i) => {
          let info = rank.submission_info
          let cellClass = {}
          Object.keys(info).forEach(problemID => {
            dataRank[i][problemID] = info[problemID]
            dataRank[i][problemID].ac_time = this.formatRankTime(dataRank[i][problemID].ac_time)
            let status = info[problemID]
            if (status.is_first_ac) {
              cellClass[problemID] = 'first-ac'
            } else if (status.is_ac) {
              cellClass[problemID] = 'ac'
            } else {
              cellClass[problemID] = 'wa'
            }
          })
          dataRank[i].cellClassName = cellClass
        })
        this.dataRank = dataRank
      },
      addTableColumns (problems) {
        // 根据题目添加table column
        problems.forEach(problem => {
          this.columns.push({
            align: 'center',
            key: problem.id,
            className: 'rank-problem-cell',
            // Element Plus defaults flex columns to at least 80px. Allow
            // each problem column to share the actual remaining width.
            minWidth: 1,
            renderHeader: (h, params) => {
              return h('a', {
                'class': {
                  'emphasis': true
                },
                on: {
                  click: () => {
                    this.$router.push({
                      name: 'contest-problem-details',
                      params: {
                        contestID: this.contestID,
                        problemID: problem._id
                      }
                    })
                  }
                }
              }, problem._id)
            },
            render: (h, params) => {
              if (params.row[problem.id]) {
                let status = params.row[problem.id]
                let acTime, errorNumber
                if (status.is_ac) {
                  acTime = h('span', {class: 'rank-problem-time'}, status.ac_time)
                }
                if (status.error_number !== 0) {
                  errorNumber = h('span', {class: 'rank-problem-errors'}, '(-' + status.error_number + ')')
                }
                return h('div', {class: 'rank-problem-result'}, [acTime, errorNumber])
              }
            }
          })
        })
      },
      parseTotalTime (totalTime) {
        return this.formatRankTime(totalTime)
      },
      formatRankTime (totalSeconds) {
        const value = Math.max(0, Number(totalSeconds) || 0)
        const hours = Math.floor(value / 3600)
        const minutes = Math.floor((value % 3600) / 60)
        return [hours, minutes].map(part => String(part).padStart(2, '0')).join(':')
      },
      downloadRankCSV () {
        utils.downloadFile(`contest_rank?download_csv=1&contest_id=${this.$route.params.contestID}&force_refresh=${this.forceUpdate ? '1' : '0'}`)
      }
    }
  }
</script>
<style scoped lang="less">
  .echarts {
    height: 320px;
    width: 100%;
    border-bottom: 1px solid var(--color-border);
  }
  .rank-title { color: var(--color-text); font-size: 15px; font-weight: 650; }
  .rank-settings-row { display: flex; min-height: 52px; align-items: center; gap: 18px; flex-wrap: wrap; margin: 0; padding: 0 16px; border-bottom: 1px solid var(--color-border); box-sizing: border-box; }
  .rank-setting { display: inline-flex; align-items: center; gap: 8px; color: var(--color-text-muted); font-size: 12px; white-space: nowrap; }
  .rank-download { display: inline-flex; min-height: 32px; align-items: center; gap: 7px; margin-left: auto; padding: 0 10px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg); color: var(--color-text-muted); font: inherit; font-size: 12px; cursor: pointer; transition: color var(--transition), border-color var(--transition), background-color var(--transition); }
  .rank-download:hover, .rank-download:focus-visible { border-color: var(--line-strong); background: var(--color-bg-subtle); color: var(--color-text); }
  .rank-download :deep(.legacy-icon) { display: inline-flex; align-items: center; line-height: 0; }
  :deep(.el-table) { --el-table-row-hover-bg-color: var(--color-bg-subtle); border-radius: var(--radius-sm); }
  :deep(.el-table th.el-table__cell) { background: #fcfbf9; color: var(--color-text-muted); font-size: 12px; }
  :deep(.el-table td.el-table__cell) { padding: 9px 0; }
  :deep(.rank-problem-cell .cell) { padding-inline: 2px; overflow: hidden; }
  :deep(.rank-problem-result) { max-width: 100%; overflow: hidden; white-space: nowrap; font-size: clamp(9px, 0.75vw, 11px); line-height: 1.1; font-variant-numeric: tabular-nums; }
  :deep(.rank-problem-time), :deep(.rank-problem-errors) { display: block; margin: 0; }
  :deep(.el-table__body tr:hover > td.el-table__cell) { background-color: var(--color-bg) !important; }
  :deep(.el-table__body tr:hover > td.el-table__cell.rank-hover-cell) { background-color: var(--color-bg-subtle) !important; }
  :deep(.el-table__body tr:hover > td.el-table__cell.first-ac),
  :deep(.el-table__body tr:hover > td.el-table__cell.ac) { background-color: var(--tag-tools-bg) !important; }
  :deep(.el-table__body tr:hover > td.el-table__cell.wa) { background-color: var(--tag-research-bg) !important; }

  @media (max-width: 760px) {
    .rank-settings-row { gap: 10px 14px; padding: 10px 12px; }
    .rank-download { width: 100%; justify-content: center; margin-left: 0; }
  }
</style>
