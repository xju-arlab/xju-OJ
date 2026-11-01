<template>
  <Panel shadow>
    <div v-if="freezeNotice" :class="['rank-freeze-banner', { 'is-live': isContestAdmin && !previewFrozen }]">
      <Icon type="ios-locked-outline" />
      <span>{{ freezeNotice }}</span>
      <template v-if="isContestAdmin">
        <label class="rank-setting"><span>选手视角</span><i-switch v-model="previewFrozen" @on-change="getContestRankData(1)"></i-switch></label>
        <button v-if="contestEnded" type="button" class="rank-unfreeze" :disabled="unfreezing" @click="unfreeze">开榜</button>
      </template>
    </div>
    <div class="rank-settings-row" aria-label="Ranking settings">
      <label class="rank-setting"><span>{{$t('m.Chart')}}</span><i-switch v-model="showChart"></i-switch></label>
      <label class="rank-setting"><span>{{$t('m.Auto_Refresh')}} (10s)</span><i-switch v-model="autoRefresh" :disabled="refreshDisabled" @on-change="handleAutoRefresh"></i-switch></label>
      <span v-if="campusBoard" class="rank-campus-setting">
        <label class="rank-setting"><span>校区区分</span><i-switch v-model="showCampus"></i-switch></label>
        <span v-if="showCampus" class="rank-campus-legend" aria-label="校区颜色">
          <span v-for="(label, code) in CAMPUSES" :key="code" :class="`is-${code}`">{{ label }}</span>
        </span>
      </span>
      <template v-if="isContestAdmin">
        <label class="rank-setting"><span>{{$t('m.RealName')}}</span><i-switch v-model="showRealName"></i-switch></label>
        <label class="rank-setting"><span>{{$t('m.Force_Update')}}</span><i-switch v-model="forceUpdate" :disabled="refreshDisabled"></i-switch></label>
      </template>
      <span v-if="awardRanges.length" class="rank-award-legend" aria-label="晋级与奖牌">
        <span v-for="range in awardRanges" :key="range.key" :class="`is-${range.key}`">{{ range.label }} {{ range.count }}</span>
      </span>
      <button v-if="isContestAdmin" type="button" class="rank-download rank-award-button" @click="awardsVisible = true">晋级 / 奖牌</button>
      <button type="button" class="rank-download" @click="downloadRankCSV">
        <Icon type="download" />
        <span>{{$t('m.download_csv')}}</span>
      </button>
    </div>
    <div v-if="showChart" class="echarts">
      <ECharts :options="options" ref="chart" auto-resize></ECharts>
    </div>
    <RankAwardsDialog v-if="isContestAdmin" v-model:visible="awardsVisible" :contest-id="$route.params.contestID" :awards="contest.rank_awards"
                      :official="officialCount" :unit="contest.team_contest ? '支' : '人'" @saved="awardsSaved" />
    <Table ref="tableRank" :columns="columns" :data="dataRank" :row-class-name="rankRowClass" disabled-hover></Table>
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
  import api from '@oj/api'
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
        unfreezing: false,
        columns: [
          {
            className: 'rank-hover-cell rank-place-column',
            align: 'center',
            // Room for a place badge and the movement arrow beside it.
            width: 80,
            fixed: 'left',
            render: (h, params) => {
              return this.renderPlace(h, params)
            }
          },
          {
            className: 'rank-hover-cell',
            isNameColumn: true,
            title: this.$t('m.User_User'),
            align: 'center',
            fixed: 'left',
            width: 150,
            render: (h, params) => {
              if (params.row.team) return this.renderTeamName(h, params.row.team)
              return this.renderUserName(h, params.row, {
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
              })
            }
          },
          {
            className: 'rank-hover-cell',
            title: this.$t('m.Rank_Solved_Problems'),
            align: 'center',
            width: 88,
            render: (h, params) => {
              // Problems solved out of the contest's problems.
              return h('span', { class: 'rank-solved' }, `${params.row.accepted_number} / ${this.contestProblems.length}`)
            }
          },
          {
            className: 'rank-hover-cell',
            title: this.$t('m.Penalty'),
            align: 'center',
            width: 72,
            render: (h, params) => {
              return h('span', { class: 'rank-penalty' }, this.penaltyMinutes(params.row.total_time))
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
          users.push(this.rankName(rank))
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
            name: this.rankName(rank),
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
            } else if (status.frozen_number) {
              // Attempted after the freeze; the result stays hidden.
              cellClass[problemID] = 'frozen'
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
                const pending = status.frozen_number ? h('span', {class: 'rank-problem-pending'}, '?+' + status.frozen_number) : null
                if (this.canOpenSubmissions(params.row)) {
                  return h('button', {
                    type: 'button',
                    class: 'rank-problem-result rank-problem-link',
                    title: '查看提交',
                    on: { click: () => this.openSubmissions(params.row, problem) }
                  }, [acTime, pending, errorNumber])
                }
                return h('div', {class: 'rank-problem-result'}, [acTime, pending, errorNumber])
              }
            }
          })
        })
      },
      rankName (rank) {
        return rank.team ? rank.team.name : rank.user.username
      },
      unfreeze () {
        // Opening the board shows everyone, signed in or not, what the freeze hid.
        this.$confirm('开榜后，所有人（包括未登录的访客）都能看到最终排名、封榜以来的名次升降和全部提交。确定开榜吗？', '确认开榜', {
          confirmButtonText: '确认开榜', cancelButtonText: '取消', type: 'warning', closeOnClickModal: false
        }).then(() => {
          this.unfreezing = true
          return api.setContestRankFreeze(this.contestID, true).then(() => {
            this.$success('已开榜')
            this.previewFrozen = false
            return this.$store.dispatch('getContest')
          }).then(() => this.getContestRankData(1)).finally(() => { this.unfreezing = false })
        }).catch(() => {})
      },
      // ACM penalty in whole minutes. The board is ordered by total seconds and
      // flooring keeps that order, so a higher team never shows a larger penalty.
      penaltyMinutes (totalSeconds) {
        return Math.floor(Math.max(0, Number(totalSeconds) || 0) / 60)
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
  :deep(.rank-solved) { color: var(--color-text); font-weight: 600; font-variant-numeric: tabular-nums; }
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
  :deep(.rank-penalty) { font-variant-numeric: tabular-nums; }
  :deep(.rank-real-name) { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  :deep(.rank-problem-link) { display: block; width: 100%; padding: 0; border: 0; background: none; color: inherit; font-family: inherit; text-align: center; cursor: pointer; }
  :deep(.rank-problem-link:hover), :deep(.rank-problem-link:focus-visible) { outline: none; text-decoration: underline; }
  // Hover follows the pointer through :hover alone. With fixed columns Element also sets a JS hover-row
  // class (30 ms debounce, then rAF) that lingers on rows the pointer already left, and fades cells for 0.25 s.
  :deep(.el-table .el-table__body td.el-table__cell) { transition: none; }
  :deep(.el-table__body tr.hover-row > td.el-table__cell) { background-color: inherit; }
  :deep(.el-table__body tr:hover > td.el-table__cell.rank-hover-cell) { background-color: var(--color-bg-subtle) !important; }
  :deep(.el-table__body td.el-table__cell.first-ac) { background-color: #157f66 !important; }
  :deep(.el-table__body td.el-table__cell.ac) { background-color: var(--tag-tools-bg) !important; }
  :deep(.el-table__body td.el-table__cell.wa) { background-color: var(--tag-research-bg) !important; }
  :deep(.el-table__body td.el-table__cell.frozen) { background-color: #e3eefa !important; }
  :deep(.rank-problem-pending) { display: block; color: #2873be; font-weight: 700; }
  :deep(.rank-team) { display: inline-block; max-width: 150px; overflow: hidden; color: var(--color-text); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; cursor: default; vertical-align: middle; }
  :deep(.rank-star-mark) { margin-right: 4px; color: #d29b16; font-size: 13px; }
  :deep(.el-table__body tr.rank-star-row > td.el-table__cell.rank-hover-cell) { background-color: #fcf9f2; }
  :deep(.rank-star-row .rank-team), :deep(.rank-star-row a) { color: var(--color-text-muted); }
  // Campus tints cover the info columns only, up to 罚时; the legend uses the same colours.
  :deep(.el-table__body tr.rank-campus-boda > td.el-table__cell.rank-hover-cell) { background-color: #f1ecfb; }
  :deep(.el-table__body tr.rank-campus-youhao > td.el-table__cell.rank-hover-cell) { background-color: #fdf0e2; }
  .rank-campus-setting { display: inline-flex; align-items: center; gap: 8px; }
  .rank-campus-legend { display: inline-flex; overflow: hidden; border: 1px solid var(--color-border); border-radius: 999px; font-size: 12px; font-weight: 600; line-height: 22px; }
  .rank-campus-legend span { padding: 0 10px; }
  .rank-campus-legend .is-boda { background: #f1ecfb; color: #6748b8; }
  .rank-campus-legend .is-youhao { border-left: 1px solid var(--color-border); background: #fdf0e2; color: #a8581b; }
  .rank-freeze-banner { display: flex; min-height: 44px; align-items: center; gap: 10px; flex-wrap: wrap; padding: 0 16px; border-bottom: 1px solid var(--color-border); background: #eef4fb; color: #2873be; font-size: 13px; }
  .rank-freeze-banner.is-live { background: var(--color-bg-subtle); color: var(--color-text-muted); }
  .rank-freeze-banner .rank-setting { margin-left: auto; }
  .rank-unfreeze { min-height: 28px; padding: 0 14px; border: 0; border-radius: var(--radius-sm); background: #2873be; color: #fff; font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; }
  .rank-unfreeze:disabled { opacity: .6; cursor: default; }

  @media (max-width: 760px) {
    .rank-settings-row { gap: 10px 14px; padding: 10px 12px; }
    .rank-download { width: 100%; justify-content: center; margin-left: 0; }
  }
</style>
