import moment from 'moment'
import api from '@oj/api'
import i18n from '@/i18n'
import { mapGetters, mapState } from '@/store/compat'
import { types } from '@/store'
import { CONTEST_STATUS } from '@/utils/constants'
import { cloneFixtures, MOCK_CONTEST_ACM_RANK, MOCK_CONTEST_OI_RANK } from '@oj/mocks/fixtures'
import { CAMPUSES } from '@/utils/teamRoster'
import { awardRanges, placeTier } from '@/utils/rankAwards'
import { readRankPreferences, updateRankPreferences } from './rankPreferences'
import RankAwardsDialog from './RankAwardsDialog.vue'

export default {
  components: { RankAwardsDialog },
  data () {
    const rankPreferences = readRankPreferences()
    return {
      autoRefresh: rankPreferences.autoRefresh,
      CAMPUSES,
      // Tints rows by campus; offered once some team on the board has one.
      showCampus: rankPreferences.campus,
      campusBoard: false,
      // Official places on the whole board, which award percentages count.
      officialCount: 0,
      awardsVisible: false,
      rankPreferences,
      rankRequestSerial: 0,
      // Contest admins see the live board; this shows them the contestants' frozen one.
      previewFrozen: false,
      boardFrozen: false
    }
  },
  methods: {
    // The official place; a star team (打星) takes none and shows *.
    rankPlace (params) {
      if (params.row.place !== undefined) return params.row.place ?? '*'
      return params.index + (this.page - 1) * this.limit + 1
    },
    // Contest admins open any team's submissions from a cell; everyone else only their own.
    canOpenSubmissions (row) {
      const me = this.$store.state.user.profile.user
      return this.isContestAdmin || Boolean(me && me.id === row.user.id)
    },
    openSubmissions (row, problem) {
      const me = this.$store.state.user.profile.user
      const query = me && me.id === row.user.id ? { problemID: problem._id, myself: '1' }
        : { problemID: problem._id, username: row.user.username }
      this.$router.push({ name: 'contest-submission-list', params: { contestID: this.contestID }, query })
    },
    // Star teams hold no place; on a team-account contest neither does any other
    // account on the board, such as an admin trying a problem.
    unofficial (row) {
      if (this.contest.team_contest) return !row.team || Boolean(row.team.star)
      return Boolean(row.team && row.team.star)
    },
    // The place, bold when it advances or wins a medal (the row then carries a
    // colour bar), and how far it moved since the freeze. The arrow hangs off
    // the number's side, so every place stays centred in its column.
    renderPlace (h, params) {
      const place = this.rankPlace(params)
      const tier = placeTier(place, this.awardRanges)
      const badge = h('span', {
        class: ['rank-place', tier ? `is-${tier.key}` : (Number.isInteger(place) ? '' : 'is-unranked')],
        title: tier ? this.$t(`m.Award_${tier.key}`) : undefined
      }, place)
      const before = params.row.frozen_place
      const moved = Number.isInteger(place) && Number.isInteger(before) ? before - place : 0
      return h('span', { class: 'rank-place-cell' }, [badge, moved ? h('span', {
        class: ['rank-move', moved > 0 ? 'is-up' : 'is-down'], title: `封榜时第 ${before} 名`
      }, (moved > 0 ? '↑' : '↓') + Math.abs(moved)) : null])
    },
    awardsSaved () {
      this.$store.dispatch('getContest')
    },
    rankRowClass ({ row, rowIndex }) {
      const campus = this.showCampus && row.team && CAMPUSES[row.team.campus] ? `rank-campus-${row.team.campus}` : ''
      const tier = placeTier(this.rankPlace({ row, index: rowIndex }), this.awardRanges)
      return [this.unofficial(row) ? 'rank-star-row' : '', campus, tier ? `rank-tier-${tier.key}` : ''].filter(Boolean).join(' ')
    },
    renderUserName (h, row, attrs) {
      return h('a', attrs, [this.unofficial(row) ? h('span', { class: 'rank-star-mark', 'aria-label': '打星' }, '★') : null, row.user.username])
    },
    // A team account shows its team name, with the members on hover.
    renderTeamName (h, team) {
      const members = team.members.length ? '队员：' + team.members.join('、') : team.name
      return h('span', { class: 'rank-team', title: (team.star ? '打星队伍 · ' : '') + members }, [
        team.star ? h('span', { class: 'rank-star-mark', 'aria-label': '打星' }, '★') : null, team.name
      ])
    },
    getContestRankData (page = 1, refresh = false) {
      this.page = Number(page) || 1
      let offset = (page - 1) * this.limit
      const requestSerial = ++this.rankRequestSerial
      const chart = this.showChart ? this.$refs.chart : null
      if (chart && !refresh) chart.showLoading({maskColor: 'rgba(255, 255, 255, 0.82)'})
      // A team board is small: fetch it whole and number its official teams here.
      const teamBoard = Boolean(this.contest.team_contest)
      let params = {
        offset: teamBoard ? 0 : offset,
        limit: teamBoard ? 250 : this.limit,
        contest_id: this.$route.params.contestID,
        force_refresh: this.forceUpdate ? '1' : '0'
      }
      if (this.previewFrozen) params.frozen = '1'
      api.getContestRank(params).then(res => {
        if (requestSerial !== this.rankRequestSerial) return
        let payload = res.data.data || {}
        const results = Array.isArray(payload.results) ? payload.results : []
        this.officialCount = teamBoard ? results.filter(row => !this.unofficial(row)).length : Number(payload.total) || results.length
        if (teamBoard) {
          this.campusBoard = results.some(row => row.team && CAMPUSES[row.team.campus])
          let place = 0
          results.forEach(row => { row.place = this.unofficial(row) ? null : ++place })
          payload = { ...payload, results: results.slice(offset, offset + this.limit) }
        }
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
          // Shares the row's background with the other info columns.
          className: 'rank-hover-cell',
          title: this.$t('m.RealName'),
          titleKey: 'm.RealName',
          align: 'center',
          // Wide enough for three three-character names on one line; longer ones end in an ellipsis.
          width: 172,
          render: (h, {row}) => {
            return h('span', { class: 'rank-real-name', title: row.user.real_name || '' }, row.user.real_name)
          }
        })
      } else if (!value && existingIndex !== -1) {
        this.columns.splice(existingIndex, 1)
      }
    }
  },
  watch: {
    // The board may load before its contest; a team board then refetches whole.
    'contest.team_contest' (team) {
      if (team) this.getContestRankData(this.page)
    },
    showCampus (value) {
      updateRankPreferences({ campus: value === true })
    },
    // Column titles are plain strings; the language can change after the board
    // is built, say once the profile arrives or a team contest turns it Chinese.
    uiLocale () {
      for (const column of this.columns) {
        if (column.titleKey) column.title = this.$t(column.titleKey)
      }
    },
    // A team-account contest ranks teams, not users.
    nameColumnTitle: {
      immediate: true,
      handler (title) {
        const column = this.columns.find(item => item.isNameColumn)
        if (column) column.title = title
      }
    }
  },
  computed: {
    ...mapGetters(['isContestAdmin', 'contestRuleType']),
    nameColumnTitle () {
      return this.contest.team_contest ? this.$t('m.Team') : this.$t('m.User_User')
    },
    awardRanges () {
      return awardRanges(this.contest.rank_awards, this.officialCount)
    },
    uiLocale () {
      return i18n.global.locale.value
    },
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
