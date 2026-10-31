import moment from 'moment'
import api from '@oj/api'
import { mapGetters, mapState } from '@/store/compat'
import { types } from '@/store'
import { CONTEST_STATUS } from '@/utils/constants'
import { cloneFixtures, MOCK_CONTEST_ACM_RANK, MOCK_CONTEST_OI_RANK } from '@oj/mocks/fixtures'
import { readRankPreferences, updateRankPreferences } from './rankPreferences'

export default {
  data () {
    const rankPreferences = readRankPreferences()
    return {
      autoRefresh: rankPreferences.autoRefresh,
      rankPreferences,
      rankRequestSerial: 0,
      // Contest admins see the live board; this shows them the contestants' frozen one.
      previewFrozen: false,
      boardFrozen: false
    }
  },
  methods: {
    getContestRankData (page = 1, refresh = false) {
      this.page = Number(page) || 1
      let offset = (page - 1) * this.limit
      const requestSerial = ++this.rankRequestSerial
      const chart = this.showChart ? this.$refs.chart : null
      if (chart && !refresh) chart.showLoading({maskColor: 'rgba(255, 255, 255, 0.82)'})
      let params = {
        offset,
        limit: this.limit,
        contest_id: this.$route.params.contestID,
        force_refresh: this.forceUpdate ? '1' : '0'
      }
      if (this.previewFrozen) params.frozen = '1'
      api.getContestRank(params).then(res => {
        if (requestSerial !== this.rankRequestSerial) return
        const payload = res.data.data || {}
        const results = Array.isArray(payload.results) ? payload.results : []
        if (results.length || this.getMockRank().length === 0) this.applyRankPayload(payload, this.page)
        else this.applyRankPayload(this.getMockRankPayload(), this.page)
      }).catch(() => {
        if (requestSerial !== this.rankRequestSerial) return
        this.applyRankPayload(this.getMockRankPayload(), this.page)
      }).finally(() => {
        if (chart && !refresh) chart.hideLoading()
      })
    },
    applyRankPayload (payload, page) {
      const results = Array.isArray(payload.results) ? payload.results : []
      this.boardFrozen = payload.frozen === true
      this.total = Number(payload.total) || results.length
      if (page === 1) this.applyToChart(results.slice(0, 10))
      this.applyToTable(results)
    },
    getMockRank () {
      return this.contestRuleType === 'ACM' ? MOCK_CONTEST_ACM_RANK : MOCK_CONTEST_OI_RANK
    },
    getMockRankPayload () {
      const mockRank = this.getMockRank()
      const start = (this.page - 1) * this.limit
      return {
        total: mockRank.length,
        results: cloneFixtures(mockRank.slice(start, start + this.limit))
      }
    },
    handleAutoRefresh (status) {
      clearInterval(this.refreshFunc)
      this.autoRefresh = status === true
      updateRankPreferences({autoRefresh: this.autoRefresh})
      if (this.autoRefresh) {
        this.refreshFunc = setInterval(() => {
          this.page = 1
          this.getContestRankData(1, true)
        }, 10000)
      }
    },
    syncRealNameColumn (value) {
      const existingIndex = this.columns.findIndex(column => column.isRealNameColumn)
      if (value && existingIndex === -1) {
        this.columns.splice(2, 0, {
          isRealNameColumn: true,
          title: this.$t('m.RealName'),
          align: 'center',
          width: 150,
          render: (h, {row}) => {
            return h('span', row.user.real_name)
          }
        })
      } else if (!value && existingIndex !== -1) {
        this.columns.splice(existingIndex, 1)
      }
    }
  },
  computed: {
    ...mapGetters(['isContestAdmin', 'contestRuleType']),
    ...mapState({
      'contest': state => state.contest.contest,
      'contestProblems': state => state.contest.contestProblems
    }),
    showChart: {
      get () {
        return this.$store.state.contest.itemVisible.chart
      },
      set (value) {
        this.$store.commit(types.CHANGE_CONTEST_ITEM_VISIBLE, {chart: value})
        updateRankPreferences({chart: value === true})
        this.$nextTick(() => {
          if (this.showChart) this.$refs.chart?.resize?.()
          this.$refs.tableRank?.handleResize?.()
        })
      }
    },
    showRealName: {
      get () {
        return this.$store.state.contest.itemVisible.realName
      },
      set (value) {
        this.$store.commit(types.CHANGE_CONTEST_ITEM_VISIBLE, {realName: value})
        updateRankPreferences({realName: value === true})
        this.syncRealNameColumn(value)
      }
    },
    forceUpdate: {
      get () {
        return this.$store.state.contest.forceUpdate
      },
      set (value) {
        this.$store.commit(types.CHANGE_RANK_FORCE_UPDATE, {value: value})
        updateRankPreferences({forceUpdate: value === true})
      }
    },
    limit: {
      get () {
        return this.$store.state.contest.rankLimit
      },
      set (value) {
        this.$store.commit(types.CHANGE_CONTEST_RANK_LIMIT, {rankLimit: value})
      }
    },
    refreshDisabled () {
      return this.contest.status === CONTEST_STATUS.ENDED
    },
    contestEnded () {
      return this.contest.status === CONTEST_STATUS.ENDED
    },
    freezeNotice () {
      const contest = this.contest
      const freeze = contest.rank_freeze_time && moment(contest.rank_freeze_time)
      const active = contest.rule_type === 'ACM' && freeze && !contest.rank_unfrozen &&
        !freeze.isAfter(moment(this.$store.state.contest.now))
      if (this.isContestAdmin ? !active : !this.boardFrozen) return ''
      const since = `已于 ${freeze.format('HH:mm')} 封榜`
      if (this.isContestAdmin && !this.previewFrozen) {
        return `${since}，你看到的是实时榜，选手看到的是封榜榜${this.contestEnded ? '' : '，比赛结束后可开榜'}`
      }
      return `${since}，此后的提交显示为 ?，比赛结束后由管理员开榜`
    }
  },
  mounted () {
    const showRealName = this.isContestAdmin && this.rankPreferences.realName
    const forceUpdate = this.isContestAdmin && this.rankPreferences.forceUpdate
    this.$store.commit(types.CHANGE_CONTEST_ITEM_VISIBLE, {
      chart: this.rankPreferences.chart,
      realName: showRealName
    })
    this.$store.commit(types.CHANGE_RANK_FORCE_UPDATE, {value: forceUpdate})
    this.syncRealNameColumn(showRealName)
    if (this.autoRefresh && !this.refreshDisabled) this.handleAutoRefresh(true)
    else this.autoRefresh = false
  },
  beforeUnmount () {
    clearInterval(this.refreshFunc)
  }
}
