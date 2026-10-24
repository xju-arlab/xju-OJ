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
                  <span v-if="isPrepContest" class="contest-prep-badge">{{ prepStateLabel }}</span>
                  <span v-else :class="['contest-status', statusClass]">{{statusLabel}}</span>
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

        <div v-if="isPrepContest" class="contest-prep-bar">
          <div class="prep-bar-info">
            <span class="prep-bar-role">{{ $t('m.Prep_Your_Role') }}：<strong>{{ prepRoleLabel(prepRole) }}</strong></span>
            <span class="prep-bar-hint">{{ $t(contest.prep_state === 'Preview' ? 'm.Prep_Preview_Hint' : 'm.Prep_Preparation_Hint') }}</span>
            <span v-if="publishedContests.length" class="prep-bar-published">
              {{ $t('m.Prep_Published_As') }}
              <router-link v-for="item in publishedContests" :key="item.id"
                           :to="{ name: 'contest-details', params: { contestID: item.id } }">#{{ item.id }} {{ item.title }}</router-link>
            </span>
          </div>
          <div v-if="canManagePrep" class="prep-bar-actions">
            <div class="prep-state-switch" role="group" :aria-label="$t('m.Contest_Preparation')">
              <button v-for="state in prepStates" :key="state" type="button"
                      :class="{ 'is-active': contest.prep_state === state }"
                      :disabled="switchingState"
                      @click="switchPrepState(state)">{{ $t(`m.Prep_State_${state}`) }}</button>
            </div>
            <a class="prep-bar-link" :href="`/admin/contest/${contestID}/edit`">{{ $t('m.Prep_Edit_Settings') }}</a>
            <el-button type="primary" size="small" :disabled="contest.prep_state !== 'Preview'"
                       :title="contest.prep_state !== 'Preview' ? $t('m.Prep_Publish_Needs_Preview') : ''"
                       @click="openPublish">{{ $t('m.Prep_Publish') }}</el-button>
          </div>
        </div>
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

    <LegacyDialog v-if="canManagePrep" :title="$t('m.Prep_Publish')" width="560px"
                  :visible="publishVisible" @update:visible="publishVisible = $event">
      <p class="prep-publish-intro">{{ $t('m.Prep_Publish_Intro') }}</p>
      <el-form label-position="top">
        <el-form-item :label="$t('m.Title')">
          <el-input v-model="publishForm.title" maxlength="128"></el-input>
        </el-form-item>
        <div class="prep-publish-grid">
          <el-form-item :label="$t('m.Contest_Start_Time')">
            <el-date-picker v-model="publishForm.start_time" type="datetime"></el-date-picker>
          </el-form-item>
          <el-form-item :label="$t('m.Contest_End_Time')">
            <el-date-picker v-model="publishForm.end_time" type="datetime"></el-date-picker>
          </el-form-item>
          <el-form-item :label="$t('m.Contest_Password')">
            <el-input v-model="publishForm.password" maxlength="32"></el-input>
          </el-form-item>
          <el-form-item :label="$t('m.Real_Time_Rank')">
            <el-switch v-model="publishForm.real_time_rank"></el-switch>
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="publishVisible = false">{{ $t('m.Cancel') }}</el-button>
        <el-button type="primary" :loading="publishing" @click="publish">{{ $t('m.Prep_Publish_Confirm') }}</el-button>
      </template>
    </LegacyDialog>
  </div>
</template>

<script>
  import moment from 'moment'
  import { mapState, mapGetters, mapActions } from '@/store/compat'
  import { types } from '@/store'
  import api from '@oj/api'
  import { CONTEST_STATUS, CONTEST_STATUS_REVERSE } from '@/utils/constants'
  import ContestAnnouncementBanner from '@oj/components/ContestAnnouncementBanner.vue'

  const PREP_STATES = ['Preparation', 'Preview']

  export default {
    name: 'ContestDetail',
    components: { ContestAnnouncementBanner },
    data () {
      return {
        routeName: '',
        contestID: '',
        timer: null,
        prepStates: PREP_STATES,
        switchingState: false,
        publishVisible: false,
        publishing: false,
        publishForm: {}
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
        }).catch(() => {
          // A missing or private contest: the API client already shows the error.
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
          : this.routeName === tab.name || (tab.activeNames || []).includes(this.routeName)
      },
      formatTime (value) {
        return value ? this.$filters.localtime(value, 'YYYY-MM-DD HH:mm') : '—'
      },
      prepRoleLabel (role) {
        return role ? this.$t(`m.Prep_Role_${role}`) : '—'
      },
      async switchPrepState (state) {
        if (state === this.contest.prep_state) return
        this.switchingState = true
        try {
          await api.setPrepContestState(this.contestID, state)
          await this.$store.dispatch('getContest')
          // Management tabs only exist while preparing.
          if (state === 'Preview' && this.prepManagementRoutes.includes(this.routeName)) {
            this.$router.push({ name: 'contest-details', params: { contestID: this.contestID } })
          }
        } catch (_) {
          // The API client already shows the error.
        } finally {
          this.switchingState = false
        }
      },
      openPublish () {
        this.publishForm = {
          title: this.contest.title,
          start_time: new Date(this.contest.start_time),
          end_time: new Date(this.contest.end_time),
          password: this.contest.password || '',
          real_time_rank: this.contest.real_time_rank !== false
        }
        this.publishVisible = true
      },
      async publish () {
        const form = this.publishForm
        if (new Date(form.end_time) <= new Date(form.start_time)) {
          this.$error(this.$t('m.Prep_Time_Invalid'))
          return
        }
        this.publishing = true
        try {
          const res = await api.publishPrepContest({
            contest_id: this.contestID,
            title: form.title,
            start_time: new Date(form.start_time).toISOString(),
            end_time: new Date(form.end_time).toISOString(),
            password: form.password,
            real_time_rank: form.real_time_rank
          })
          this.publishVisible = false
          this.$success(this.$t('m.Prep_Published'))
          this.$router.push({ name: 'contest-details', params: { contestID: res.data.data.id } })
        } catch (_) {
          // The API client already shows the error.
        } finally {
          this.publishing = false
        }
      }
    },
    computed: {
      ...mapState({
        contest: state => state.contest.contest,
        now: state => state.contest.now
      }),
      ...mapGetters([
        'contestMenuDisabled', 'contestRuleType', 'contestStatus', 'isContestAdmin',
        'isAuthenticated', 'OIContestRealTimePermission',
        'isPrepContest', 'prepRole', 'canManagePrep', 'canAuthorPrep', 'canEditPrep'
      ]),
      prepManagementRoutes () {
        return ['contest-prep-problems', 'contest-prep-problem-create', 'contest-prep-problem-edit', 'contest-prep-roles']
      },
      publishedContests () {
        return this.contest.published_contests || []
      },
      prepStateLabel () {
        return this.$t(this.contest.prep_state === 'Preview' ? 'm.Prep_State_Preview' : 'm.Prep_State_Preparation')
      },
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
        if (this.isPrepContest && this.contest.prep_state === 'Preparation') {
          return [
            { name: 'contest-details', label: 'Overview', icon: 'home', route: { name: 'contest-details', params: common } },
            { name: 'contest-problem-list', label: 'Problems', icon: 'ios-photos', route: { name: 'contest-problem-list', params: common } },
            { name: 'contest-prep-problems', label: 'Prep_Problem_Setting', icon: 'upload', route: { name: 'contest-prep-problems', params: common }, visible: this.canAuthorPrep, activeNames: ['contest-prep-problem-create', 'contest-prep-problem-edit'] },
            { name: 'contest-prep-roles', label: 'Prep_Roles', icon: 'users', route: { name: 'contest-prep-roles', params: common } },
            { name: 'contest-submission-list', label: 'Submissions', icon: 'navicon-round', route: { name: 'contest-submission-list', params: common } }
          ]
        }
        return [
          { name: 'contest-details', label: 'Overview', icon: 'home', route: { name: 'contest-details', params: common } },
          { name: 'contest-announcement-list', label: 'Announcements', icon: 'megaphone', route: { name: 'contest-announcement-list', params: common }, disabled: this.contestMenuDisabled },
          { name: 'contest-problem-list', label: 'Problems', icon: 'ios-photos', route: { name: 'contest-problem-list', params: common } },
          { name: 'contest-submission-list', label: 'Submissions', icon: 'navicon-round', route: { name: 'contest-submission-list', params: common }, disabled: this.contestMenuDisabled, visible: this.OIContestRealTimePermission },
          { name: 'contest-rank', label: 'Rankings', icon: 'stats-bars', route: { name: 'contest-rank', params: common }, disabled: this.contestMenuDisabled, visible: this.OIContestRealTimePermission },
          { name: 'acm-helper', label: 'Admin_Helper', icon: 'shield', route: { name: 'acm-helper', params: common }, visible: this.showAdminHelper && !this.isPrepContest }
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
        if (this.isPrepContest) return this.$t('m.Contest_Preparation')
        if (this.contestStatus === CONTEST_STATUS.NOT_START) return this.$t('m.Not_Started')
        if (this.contestStatus === CONTEST_STATUS.ENDED) return this.$t('m.Ended')
        return this.$t('m.Underway')
      },
      countdownValue () {
        if (this.isPrepContest) return this.prepStateLabel
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

.contest-prep-badge {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 9px;
  border-radius: var(--radius-sm);
  background: var(--tag-tools-bg);
  color: var(--color-link);
  font-size: 12px;
  font-weight: 650;
}
.contest-prep-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px 18px;
  margin-top: 16px;
  padding: 12px 14px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-subtle);
}
.prep-bar-info { display: flex; flex-direction: column; gap: 4px; min-width: 0; color: var(--color-text-muted); font-size: 13px; }
.prep-bar-role strong { color: var(--color-text); }
.prep-bar-hint { color: var(--color-text-faint); font-size: 12px; }
.prep-bar-published { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 12px; }
.prep-bar-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.prep-bar-link { color: var(--color-link); font-size: 13px; }
.prep-state-switch {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  button {
    height: 30px;
    padding: 0 12px;
    border: 0;
    background: var(--color-bg);
    color: var(--color-text-muted);
    font-size: 13px;
    cursor: pointer;
    & + button { border-left: 1px solid var(--color-border); }
    &.is-active { background: var(--color-link); color: #fff; }
    &:disabled { cursor: wait; }
  }
}
.prep-publish-intro { margin: 0 0 12px; color: var(--color-text-muted); font-size: 13px; line-height: 1.6; }
.prep-publish-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
.prep-publish-grid :deep(.el-date-editor.el-input) { width: 100%; }
@media (max-width: 560px) {
  .prep-publish-grid { grid-template-columns: 1fr; }
}
</style>
