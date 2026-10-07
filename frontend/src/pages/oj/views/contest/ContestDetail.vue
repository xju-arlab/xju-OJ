<template>
  <div :class="['contest-detail-page', { 'is-problem-page': isProblemRoute }]">
    <ContestAnnouncementBanner v-if="!isProblemRoute && canReadAnnouncements" :key="contestID" :contest-id="contestID" />
    <template v-if="!isProblemRoute">
      <section class="contest-hero" aria-labelledby="contest-title">
        <div class="contest-breadcrumb">
          <router-link :to="{ name: 'contest-list' }">{{$t('m.Contests')}}</router-link>
          <span aria-hidden="true">/</span>
          <span>{{contestID}}</span>
        </div>

        <div class="contest-hero-main">
          <div class="contest-heading">
            <span class="contest-mark" aria-hidden="true"><Icon type="trophy" /></span>
            <div>
              <div class="contest-title-line">
                <h1 id="contest-title">{{contest.title || $t('m.Contests')}}</h1>
                <div class="contest-title-badges">
                  <span :class="['contest-rule', ruleClass]">{{contest.rule_type || 'ACM'}}</span>
                  <span :class="['contest-status', statusClass]">{{statusLabel}}</span>
                  <span v-if="contest.contest_type && contest.contest_type !== 'Public' && !contestEnded" class="contest-private">
                    <Icon type="ios-locked-outline" />
                    {{contestTypeLabel}}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div class="contest-countdown" :aria-label="statusLabel">
            <span>{{countdownCaption}}</span>
            <strong>{{countdownValue}}</strong>
          </div>
        </div>

        <dl class="contest-meta">
          <div>
            <dt><Icon type="calendar" />{{$t('m.StartAt')}}</dt>
            <dd>{{formatTime(contest.start_time)}}</dd>
          </div>
          <div>
            <dt><Icon type="calendar" />{{$t('m.EndAt')}}</dt>
            <dd>{{formatTime(contest.end_time)}}</dd>
          </div>
          <div>
            <dt><Icon type="android-time" />{{$t('m.Duration')}}</dt>
            <dd>{{durationLabel}}</dd>
          </div>
          <div>
            <dt><Icon type="user-circle" />{{$t('m.Creator')}}</dt>
            <dd>{{creatorName}}</dd>
          </div>
        </dl>
      </section>

      <nav class="contest-tabs" :aria-label="$t('m.Contests')">
        <button v-for="tab in visibleTabs"
                :key="tab.name"
                type="button"
                :class="['contest-tab', { 'is-active': isTabActive(tab), 'is-disabled': tab.disabled }]"
                :disabled="tab.disabled"
                @click="openTab(tab)">
          <Icon :type="tab.icon" />
          <span>{{$t(`m.${tab.label}`)}}</span>
        </button>
      </nav>
    </template>

    <main :class="['contest-content', { 'is-root': routeName === 'contest-details' }]">
      <div v-if="routeName === 'contest-details'" class="contest-overview-grid">
        <section class="contest-overview" aria-labelledby="contest-overview-title">
          <div class="section-heading">
            <span class="section-icon"><Icon type="file-text" /></span>
            <div>
              <p>{{$t('m.Contests')}}</p>
              <h2 id="contest-overview-title">{{$t('m.Overview')}}</h2>
            </div>
          </div>
          <div v-if="contest.description" class="markdown-body contest-description" v-html="contest.description"></div>
          <p v-else class="contest-empty">{{$t('m.No_contest')}}</p>

        </section>

        <aside class="contest-guide" aria-labelledby="contest-guide-title">
          <div class="section-heading compact">
            <span class="section-icon"><Icon type="info-circle" /></span>
            <div>
              <p>XJU-OJ</p>
              <h2 id="contest-guide-title">{{$t('m.ContestType')}}</h2>
            </div>
          </div>
          <dl>
            <div><dt>{{$t('m.Rule')}}</dt><dd :class="['contest-rule', ruleClass]">{{contest.rule_type || 'ACM'}}</dd></div>
            <div><dt>{{$t('m.ContestType')}}</dt><dd>{{contestTypeLabel}}</dd></div>
            <div><dt>{{$t('m.Problems')}}</dt><dd>{{contestProblemIds.length || '—'}}</dd></div>
            <div><dt>{{$t('m.Status')}}</dt><dd :class="['contest-status', statusClass]">{{statusLabel}}</dd></div>
          </dl>
          <button type="button"
                  class="contest-primary-link"
                  @click="openProblems">
            <span>{{$t('m.Problems_List')}}</span>
            <Icon type="arrow-down-b" />
          </button>
        </aside>
      </div>

      <router-view v-else v-slot="{ Component }">
        <component :is="Component" />
      </router-view>
    </main>
  </div>
</template>

<script>
  import moment from 'moment'
  import { mapState, mapGetters, mapActions } from '@/store/compat'
  import { types } from '@/store'
  import { CONTEST_STATUS, CONTEST_STATUS_REVERSE } from '@/utils/constants'
  import ContestAnnouncementBanner from '@oj/components/ContestAnnouncementBanner.vue'

  export default {
    name: 'ContestDetail',
    components: { ContestAnnouncementBanner },
    data () {
      return {
        routeName: '',
        contestID: '',
        timer: null
      }
    },
    mounted () {
      this.syncRoute()
      this.loadContest()
    },
    methods: {
      ...mapActions(['changeDomTitle']),
      syncRoute () {
        this.routeName = this.$route.name
        this.contestID = this.$route.params.contestID
      },
      loadContest () {
        this.$store.dispatch('getContest').then(res => {
          const data = res.data.data
          if (data.rule_type === 'AI') return this.$router.replace({ name: 'ai-contest', params: { contestID: data.id } })
          this.changeDomTitle({ title: data.title })
          clearInterval(this.timer)
          if (moment(data.end_time).isAfter(moment(data.now))) {
            this.timer = setInterval(() => this.$store.commit(types.NOW_ADD_1S), 1000)
          }
        })
      },
      openTab (tab) {
        if (!tab.disabled && !this.isTabActive(tab)) this.$router.push(tab.route)
      },
      openProblems () {
        this.openTab(this.tabs.find(tab => tab.name === 'contest-problem-list'))
      },
      isTabActive (tab) {
        return tab.name === 'contest-details'
          ? this.routeName === 'contest-details'
          : this.routeName === tab.name
      },
      formatTime (value) {
        return value ? this.$filters.localtime(value, 'YYYY-MM-DD HH:mm') : '—'
      }
    },
    computed: {
      ...mapState({
        contest: state => state.contest.contest,
        now: state => state.contest.now
      }),
      ...mapGetters([
        'contestMenuDisabled', 'contestRuleType', 'contestStatus', 'isContestAdmin',
        'isAuthenticated', 'OIContestRealTimePermission'
      ]),
      canReadAnnouncements () {
        if (!this.isAuthenticated || !this.contestID || String(this.contest.id) !== String(this.contestID)) return false
        return !this.contestMenuDisabled && (this.contestStatus !== CONTEST_STATUS.NOT_START || this.isContestAdmin)
      },
      isProblemRoute () {
        return this.routeName === 'contest-problem-details'
      },
      contestEnded () {
        return this.contestStatus === CONTEST_STATUS.ENDED
      },
      tabs () {
        const common = { contestID: this.contestID }
        return [
          { name: 'contest-details', label: 'Overview', icon: 'home', route: { name: 'contest-details', params: common } },
          { name: 'contest-announcement-list', label: 'Announcements', icon: 'megaphone', route: { name: 'contest-announcement-list', params: common }, disabled: this.contestMenuDisabled },
          { name: 'contest-problem-list', label: 'Problems', icon: 'ios-photos', route: { name: 'contest-problem-list', params: common } },
          { name: 'contest-submission-list', label: 'Submissions', icon: 'navicon-round', route: { name: 'contest-submission-list', params: common }, disabled: this.contestMenuDisabled, visible: this.OIContestRealTimePermission },
          { name: 'contest-rank', label: 'Rankings', icon: 'stats-bars', route: { name: 'contest-rank', params: common }, disabled: this.contestMenuDisabled, visible: this.OIContestRealTimePermission },
          { name: 'acm-helper', label: 'Admin_Helper', icon: 'shield', route: { name: 'acm-helper', params: common }, visible: this.showAdminHelper }
        ]
      },
      visibleTabs () {
        return this.tabs.filter(tab => tab.visible !== false)
      },
      showAdminHelper () {
        return this.isContestAdmin && this.contestRuleType === 'ACM'
      },
      contestProblemIds () {
        return (this.contest.problem_ids || this.contest.problems || []).map(problem => {
          if (typeof problem === 'string' || typeof problem === 'number') return String(problem)
          return problem._id || problem.id || ''
        }).filter(Boolean)
      },
      ruleClass () {
        return String(this.contest.rule_type).toUpperCase() === 'OI' ? 'rule-oi' : 'rule-acm'
      },
      statusClass () {
        if (this.contestStatus === CONTEST_STATUS.NOT_START) return 'status-not-started'
        if (this.contestStatus === CONTEST_STATUS.ENDED) return 'status-ended'
        return 'status-underway'
      },
      statusLabel () {
        const item = CONTEST_STATUS_REVERSE[this.contestStatus]
        return item ? this.$t(`m.${item.name.replace(/ /g, '_')}`) : this.$t('m.Status')
      },
      countdownCaption () {
        if (this.contestStatus === CONTEST_STATUS.NOT_START) return this.$t('m.Not_Started')
        if (this.contestStatus === CONTEST_STATUS.ENDED) return this.$t('m.Ended')
        return this.$t('m.Underway')
      },
      countdownValue () {
        if (this.contestStatus === CONTEST_STATUS.ENDED) return this.$t('m.Ended')
        const target = this.contestStatus === CONTEST_STATUS.NOT_START ? this.contest.start_time : this.contest.end_time
        if (!target) return '—'
        const seconds = Math.max(moment(target).diff(this.now, 'seconds'), 0)
        const duration = moment.duration(seconds, 'seconds')
        const days = Math.floor(duration.asDays())
        const clock = [Math.floor(duration.asHours()) % 24, duration.minutes(), duration.seconds()]
          .map(value => String(value).padStart(2, '0')).join(':')
        return days ? `${days}d ${clock}` : clock
      },
      durationLabel () {
        if (!this.contest.start_time || !this.contest.end_time) return '—'
        const hours = Math.abs(moment(this.contest.end_time).diff(moment(this.contest.start_time), 'minutes')) / 60
        if (hours >= 24) return `${Number((hours / 24).toFixed(1))}d`
        return `${Number(hours.toFixed(1))}h`
      },
      creatorName () {
        return (this.contest.created_by && this.contest.created_by.username) || 'XJU-ICTHub'
      },
      contestTypeLabel () {
        const type = this.contest.contest_type || 'Public'
        return this.$t(`m.${type.replace(/ /g, '_')}`)
      }
    },
    watch: {
      '$route' (route, previous) {
        const contestChanged = String(route.params.contestID || '') !== String(previous.params.contestID || '')
        this.syncRoute()
        if (contestChanged) this.loadContest()
        else this.changeDomTitle({ title: this.contest.title })
      }
    },
    beforeUnmount () {
      clearInterval(this.timer)
      this.$store.commit(types.CLEAR_CONTEST)
    }
  }
</script>

<style scoped lang="less">
@import "@/styles/contest-detail.less";
</style>
