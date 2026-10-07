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
  .contest-detail-page { width: 100%; color: var(--color-text); }

  .contest-hero {
    overflow: hidden;
    padding: 26px 30px 0;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
    background:
      radial-gradient(circle at 86% 12%, rgba(35, 131, 226, .08), transparent 28%),
      radial-gradient(circle at 12% 100%, rgba(15, 123, 108, .07), transparent 34%),
      linear-gradient(135deg, #fff 0%, #fcfbf8 100%);
  }

  .contest-breadcrumb { display: flex; align-items: center; gap: 8px; color: var(--color-text-faint); font-size: 12px; }
  .contest-breadcrumb a { color: var(--color-text-muted); }
  .contest-breadcrumb a:hover { color: var(--color-text); }

  .contest-hero-main { display: flex; align-items: flex-end; justify-content: space-between; gap: 28px; margin-top: 22px; }
  .contest-heading { display: flex; min-width: 0; align-items: center; gap: 16px; }
  .contest-mark {
    display: inline-flex;
    flex: 0 0 52px;
    width: 52px;
    height: 52px;
    align-items: center;
    justify-content: center;
    border: 1px solid rgba(217, 115, 13, .18);
    border-radius: var(--radius-lg);
    background: var(--tag-course-bg);
    color: var(--cat-course);
  }
  .contest-mark :deep(svg) { width: 24px; height: 24px; }
  .contest-title-line { display: flex; min-width: 0; align-items: center; flex-wrap: wrap; gap: 10px 12px; }
  .contest-title-badges { display: inline-flex; flex: none; align-items: center; flex-wrap: wrap; gap: 8px; }
  .contest-heading h1 { min-width: 0; margin: 0; font-family: var(--font-serif); font-size: clamp(25px, 3vw, 38px); font-weight: 650; line-height: 1.15; letter-spacing: -.025em; }

  .contest-rule { display: inline-flex; align-items: center; font-weight: 750; letter-spacing: .025em; }
  .rule-oi { color: var(--cat-recommend); }
  .rule-acm { color: var(--cat-course); }
  .contest-status, .contest-private {
    display: inline-flex;
    min-height: 24px;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: var(--radius-sm);
    font-size: 12px;
    font-weight: 650;
    line-height: 1;
    text-decoration: none;
  }
  .status-not-started { background: var(--tag-tools-bg); color: var(--cat-tools); }
  .status-underway { background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
  .status-ended { background: var(--color-bg-subtle); color: var(--color-text-muted); }
  .contest-private { background: var(--color-bg-subtle); color: var(--color-text-muted); }
  .contest-private :deep(svg) { width: 13px; height: 13px; }

  .contest-countdown { display: flex; flex: 0 0 auto; flex-direction: column; align-items: flex-end; padding-bottom: 2px; }
  .contest-countdown span { color: var(--color-text-muted); font-size: 11px; font-weight: 650; letter-spacing: .08em; text-transform: uppercase; }
  .contest-countdown strong { margin-top: 4px; font-family: var(--font-mono); font-size: 23px; font-variant-numeric: tabular-nums; letter-spacing: -.03em; }

  .contest-meta { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 26px -30px 0; border-top: 1px solid var(--color-border); }
  .contest-meta > div { min-width: 0; padding: 14px 18px; border-right: 1px solid var(--color-border); }
  .contest-meta > div:last-child { border-right: 0; }
  .contest-meta dt { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; color: var(--color-text-faint); font-size: 11px; font-weight: 650; }
  .contest-meta dt :deep(svg) { width: 13px; height: 13px; }
  .contest-meta dd { overflow: hidden; margin: 0; font-size: 13px; font-weight: 550; text-overflow: ellipsis; white-space: nowrap; }

  .contest-tabs {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    padding: 8px 10px;
    border: 1px solid var(--color-border);
    border-top: 0;
    border-radius: 0 0 var(--radius-lg) var(--radius-lg);
    background: var(--color-bg);
  }
  .contest-tab {
    display: inline-flex;
    min-height: 34px;
    align-items: center;
    gap: 7px;
    padding: 0 11px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-muted);
    font: inherit;
    font-size: 13px;
    cursor: pointer;
    transition: background-color var(--transition), color var(--transition);
  }
  .contest-tab :deep(svg) { width: 15px; height: 15px; }
  .contest-tab :deep(.legacy-icon) { display: inline-flex; flex: none; align-items: center; justify-content: center; line-height: 0; }
  .contest-tab :deep(.legacy-icon svg) { display: block; }
  .contest-tab > span { display: inline-flex; align-items: center; line-height: 1; }
  .contest-tab:hover:not(:disabled), .contest-tab:focus-visible:not(:disabled), .contest-tab.is-active { background: var(--color-bg-subtle); color: var(--color-text); }
  .contest-tab.is-active { font-weight: 650; }
  .contest-tab:focus-visible { outline: 2px solid rgba(55, 53, 47, .18); outline-offset: 1px; }
  .contest-tab:disabled { cursor: not-allowed; opacity: .42; }

  .contest-content { margin-top: 20px; }
  .contest-content.is-root { margin-bottom: 28px; }
  .contest-detail-page.is-problem-page .contest-content { margin-top: 0; }
  .contest-overview-grid { display: grid; grid-template-columns: minmax(0, 1fr) 290px; gap: 20px; }
  .contest-overview, .contest-guide { border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg); box-shadow: var(--shadow-card); }
  .contest-overview { min-height: 270px; padding: 24px 26px; }
  .contest-guide { align-self: start; padding: 20px; }
  .section-heading { display: flex; align-items: center; gap: 11px; padding-bottom: 17px; border-bottom: 1px solid var(--color-border); }
  .section-heading.compact { padding-bottom: 14px; }
  .section-heading p { margin: 0 0 2px; color: var(--color-text-faint); font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
  .section-heading h2 { margin: 0; font-family: var(--font-serif); font-size: 20px; font-weight: 650; }
  .section-icon { display: inline-flex; align-items: center; justify-content: center; color: var(--color-text-muted); }
  .section-icon :deep(svg) { width: 20px; height: 20px; }
  .contest-description { padding-top: 18px; }
  .contest-empty { color: var(--color-text-muted); }

  .contest-guide dl { margin: 4px 0 0; }
  .contest-guide dl > div { display: flex; min-height: 42px; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--color-border); }
  .contest-guide dt { color: var(--color-text-muted); font-size: 12px; }
  .contest-guide dd { margin: 0; font-size: 13px; font-weight: 600; text-align: right; }
  .contest-guide .contest-status { min-height: 22px; }
  .contest-primary-link {
    display: flex;
    width: 100%;
    height: 38px;
    align-items: center;
    justify-content: space-between;
    margin-top: 16px;
    padding: 0 12px;
    border: 1px solid var(--color-text);
    border-radius: var(--radius-sm);
    background: var(--color-text);
    color: #fff;
    font: inherit;
    font-size: 13px;
    font-weight: 650;
    cursor: pointer;
    transition: opacity var(--transition), transform var(--transition);
  }
  .contest-primary-link :deep(svg) { width: 14px; height: 14px; transform: rotate(-90deg); }
  .contest-primary-link:hover:not(:disabled) { opacity: .88; }
  .contest-primary-link:active:not(:disabled) { transform: translateY(1px); }
  .contest-primary-link:disabled { cursor: not-allowed; opacity: .35; }

  @media (max-width: 900px) {
    .contest-overview-grid { grid-template-columns: 1fr; }
    .contest-guide { width: auto; }
    .contest-meta { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .contest-meta > div:nth-child(2) { border-right: 0; }
    .contest-meta > div:nth-child(-n+2) { border-bottom: 1px solid var(--color-border); }
  }

  @media (max-width: 620px) {
    .contest-hero { padding: 20px 18px 0; }
    .contest-hero-main { align-items: flex-start; flex-direction: column; gap: 18px; }
    .contest-heading { align-items: flex-start; }
    .contest-mark { flex-basis: 42px; width: 42px; height: 42px; border-radius: var(--radius-md); }
    .contest-countdown { align-items: flex-start; }
    .contest-countdown strong { font-size: 20px; }
    .contest-meta { margin-right: -18px; margin-left: -18px; grid-template-columns: 1fr; }
    .contest-meta > div { border-right: 0; border-bottom: 1px solid var(--color-border); }
    .contest-meta > div:last-child { border-bottom: 0; }
    .contest-tabs { align-items: stretch; }
    .contest-tab { flex: 1 1 calc(50% - 4px); justify-content: flex-start; }
    .contest-overview { padding: 20px 18px; }
  }

  @media (prefers-reduced-motion: reduce) {
    .contest-tab, .contest-primary-link { transition: none; }
  }
</style>
