<template>
  <Panel shadow>
    <div class="rank-settings-row" aria-label="Ranking settings">
      <label class="rank-setting"><span>{{$t('m.Chart')}}</span><i-switch v-model="showChart"></i-switch></label>
      <label class="rank-setting"><span>{{$t('m.Auto_Refresh')}} (10s)</span><i-switch v-model="autoRefresh" :disabled="refreshDisabled" @on-change="handleAutoRefresh"></i-switch></label>
      <label v-if="isContestAdmin" class="rank-setting"><span>{{$t('m.RealName')}}</span><i-switch v-model="showRealName"></i-switch></label>
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
  import { mapActions } from '@/store/compat'

  import Pagination from '@oj/components/Pagination'
  import ContestRankMixin from './contestRankMixin'
  import utils from '@/utils/utils'

  export default {
    name: 'oi-contest-rank',
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
            align: 'center',
            width: 60,
            render: (h, params) => {
              return h('span', {}, params.index + (this.page - 1) * this.limit + 1)
            }
          },
          {
            title: this.$t('m.User_User'),
            align: 'center',
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
            title: this.$t('m.Total_Score'),
            align: 'center',
            render: (h, params) => {
              return h('a', {
                on: {
                  click: () => {
                    this.$router.push({
                      name: 'contest-submission-list',
                      query: {username: params.row.user.username}
                    })
                  }
                }
              }, params.row.total_score)
            }
          }
        ],
        dataRank: [],
        options: {
          color: ['#2383e2'],
          title: {
            text: this.$t('m.Top_10_Teams'),
            left: 'center'
          },
          tooltip: {
            trigger: 'axis'
          },
          toolbox: {
            show: true,
            feature: {
              dataView: {show: true, readOnly: true},
              magicType: {show: true, type: ['line', 'bar']},
              saveAsImage: {show: true}
            },
            right: '10%'
          },
          calculable: true,
          xAxis: [
            {
              type: 'category',
              data: ['root'],
              boundaryGap: true,
              axisLabel: {
                color: '#787774',
                interval: 0,
                showMinLabel: true,
                showMaxLabel: true,
                align: 'center',
                formatter: (value, index) => {
                  return utils.breakLongWords(value, 14)
                }
              },
              axisTick: {
                alignWithLabel: true
              },
              axisLine: {lineStyle: {color: '#d9d8d4'}}
            }
          ],
          yAxis: [
            {
              type: 'value',
              axisLine: {show: true, lineStyle: {color: '#d9d8d4'}},
              axisLabel: {color: '#787774'},
              splitLine: {lineStyle: {color: '#edebe8'}}
            }
          ],
          series: [
            {
              name: this.$t('m.Score'),
              type: 'bar',
              barMaxWidth: '80',
              itemStyle: {color: '#2383e2', borderRadius: [4, 4, 0, 0]},
              data: [0],
              markPoint: {
                data: [
                  {type: 'max', name: 'max'}
                ]
              }
            }
          ]
        }
      }
    },
    mounted () {
      this.contestID = this.$route.params.contestID
      this.getContestRankData(1)
      if (this.contestProblems.length === 0) {
        this.getContestProblems().then((res) => {
          this.addTableColumns(res.data.data)
        })
      } else {
        this.addTableColumns(this.contestProblems)
      }
    },
    methods: {
      ...mapActions(['getContestProblems']),
      applyToChart (rankData) {
        let [usernames, scores] = [[], []]
        rankData.forEach(ele => {
          usernames.push(ele.user.username)
          scores.push(ele.total_score)
        })
        this.options.xAxis[0].data = usernames
        this.options.series[0].data = scores
      },
      applyToTable (data) {
        // deepcopy
        let dataRank = JSON.parse(JSON.stringify(data))
        // 从submission_info中取出相应的problem_id 放入到父object中,这么做主要是为了适应iview table的data格式
        // 见https://www.iviewui.com/components/table
        dataRank.forEach((rank, i) => {
          let info = rank.submission_info
          Object.keys(info).forEach(problemID => {
            dataRank[i][problemID] = info[problemID]
          })
        })
        this.dataRank = dataRank
      },
      addTableColumns (problems) {
        problems.forEach(problem => {
          this.columns.push({
            align: 'center',
            key: problem.id,
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
              return h('span', params.row[problem.id])
            }
          })
        })
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
  .rank-settings-row { display: flex; min-height: 52px; align-items: center; gap: 18px; flex-wrap: wrap; margin: 0; padding: 0 16px; border-bottom: 1px solid var(--color-border); box-sizing: border-box; }
  .rank-setting { display: inline-flex; align-items: center; gap: 8px; color: var(--color-text-muted); font-size: 12px; white-space: nowrap; }
  .rank-download { display: inline-flex; min-height: 32px; align-items: center; gap: 7px; margin-left: auto; padding: 0 10px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg); color: var(--color-text-muted); font: inherit; font-size: 12px; cursor: pointer; transition: color var(--transition), border-color var(--transition), background-color var(--transition); }
  .rank-download:hover, .rank-download:focus-visible { border-color: var(--line-strong); background: var(--color-bg-subtle); color: var(--color-text); }
  .rank-download :deep(.legacy-icon) { display: inline-flex; align-items: center; line-height: 0; }
  :deep(.el-table) { --el-table-row-hover-bg-color: var(--color-bg-subtle); border-radius: var(--radius-sm); }
  :deep(.el-table th.el-table__cell) { background: #fcfbf9; color: var(--color-text-muted); font-size: 12px; }
  :deep(.el-table td.el-table__cell) { padding: 9px 0; }

  @media (max-width: 760px) {
    .rank-settings-row { gap: 10px 14px; padding: 10px 12px; }
    .rank-download { width: 100%; justify-content: center; margin-left: 0; }
  }
</style>
