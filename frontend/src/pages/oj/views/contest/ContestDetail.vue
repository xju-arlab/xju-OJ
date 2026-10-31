<template>
  <div :class="['contest-detail-page', { 'is-problem-page': isProblemRoute }]">
    <ContestAnnouncementBanner v-if="!isProblemRoute && canReadAnnouncements" :key="contestID" :contest-id="contestID" />
    <template v-if="!isProblemRoute">
      <section class="contest-hero" aria-labelledby="contest-title">
        <div class="contest-breadcrumb">
          <span v-if="myTeam">{{$t('m.Contests')}}</span>
          <router-link v-else :to="{ name: 'contest-list' }">{{$t('m.Contests')}}</router-link>
          <span aria-hidden="true">/</span>
          <span>{{contestID}}</span>
          <span v-if="myTeam" class="contest-team" :title="myTeam.members.length ? '队员：' + myTeam.members.join('、') : ''">
            <Icon type="users" /><strong>{{ myTeam.name }}</strong>
            <button type="button" @click="teamLogout">退出</button>
          </span>
        </div>

        <div class="contest-hero-main">
          <div class="contest-heading">
            <span class="contest-mark" aria-hidden="true"><Icon type="trophy" /></span>
            <div>
              <div class="contest-title-line">
                <h1 id="contest-title">{{contest.title || $t('m.Contests')}}</h1>
                <div class="contest-title-badges">
                  <span :class="['contest-rule', ruleClass]">{{contest.rule_type || 'ACM'}}</span>
                  <template v-if="isPrepContest">
                    <span :class="['contest-prep-badge', { 'is-review': isPrepReviewView }]">{{ prepStateLabel }}</span>
                    <span v-if="prepRole" :class="['contest-prep-role', `is-${prepRole.toLowerCase()}`]">{{ $t(`m.Prep_Role_${prepRole}`) }}</span>
                    <router-link v-for="item in publishedContests" :key="item.id" class="contest-prep-published"
                                 :to="{ name: 'contest-details', params: { contestID: item.id } }"
                                 :title="item.title">{{ $t('m.Prep_Published_As') }} #{{ item.id }}</router-link>
                  </template>
                  <span v-else :class="['contest-status', statusClass]">{{statusLabel}}</span>
                  <span v-if="!isPrepContest && contest.contest_type && contest.contest_type !== 'Public' && !contestEnded" class="contest-private">
                    <Icon type="ios-locked-outline" />
                    {{contestTypeLabel}}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="!isPrepContest || isPrepReviewView" class="contest-countdown" :aria-label="countdownCaption">
            <span>{{countdownCaption}}</span>
            <strong>{{countdownValue}}</strong>
          </div>
        </div>

        <dl class="contest-meta">
          <div>
            <dt><Icon type="calendar" />{{$t('m.StartAt')}}</dt>
            <dd>{{formatTime(metaStart)}}</dd>
          </div>
          <div>
            <dt><Icon type="calendar" />{{$t('m.EndAt')}}</dt>
            <dd>{{formatTime(metaEnd)}}</dd>
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
        <div v-if="isPrepContest && prepRole && isPrepSettingView" class="prep-controls">
          <!-- Review and publish open in a new tab; this setting page stays where it is. -->
          <button type="button" class="prep-action" @click="openExport">
            <Icon type="download" />
            <span>{{ $t('m.Prep_Export_PDF') }}</span>
          </button>
          <button type="button" class="prep-action" @click="openReview">
            <Icon type="flask" />
            <span>{{ $t('m.Prep_Review') }}</span>
            <span v-if="reviewRunning" class="prep-live" :title="$t('m.Prep_State_Review')"></span>
          </button>
          <template v-if="canManagePrep">
            <button type="button" class="prep-publish" @click="openPublish">{{ $t('m.Prep_Publish') }}</button>
            <el-tooltip :content="$t('m.Prep_Edit_Settings')" placement="top">
              <a class="prep-settings" :href="`/admin/contest/${contestID}/edit`" :aria-label="$t('m.Prep_Edit_Settings')">
                <Icon type="settings" />
              </a>
            </el-tooltip>
          </template>
        </div>
        <div v-else-if="isPrepContest && prepRole" class="prep-controls">
          <button v-if="canManagePrep && reviewRunning" type="button" class="prep-action is-danger"
                  :disabled="endingReview" @click="endReview">
            <Icon type="close" />
            <span>{{ $t('m.Prep_Review_End') }}</span>
          </button>
          <router-link class="prep-back" :to="{ name: 'contest-prep-problems', params: { contestID } }">
            <Icon type="arrow-left" />
            <span>{{ $t('m.Prep_Back_To_Setting') }}</span>
          </router-link>
        </div>
      </nav>
    </template>

    <main :class="['contest-content', { 'is-root': routeName === 'contest-details' }]">
      <!-- The member's own share of the problem plan, on every setting tab. -->
      <div v-if="isPrepSettingView && myPlan && myPlan.assigned"
           :class="['prep-my-progress', { 'is-done': myPlan.assigned && myPlan.uploaded >= myPlan.assigned }]"
           :title="$t('m.Prep_My_Progress')">
        <span>{{ $t('m.Prep_My_Progress') }}</span>
        <span class="my-progress-track" aria-hidden="true">
          <span class="my-progress-fill" :style="{ width: `${myProgressPercent}%` }"></span>
        </span>
        <strong>{{ myPlan.uploaded }} / {{ myPlan.assigned }}</strong>
      </div>
      <!-- Review runs like the real contest, so everyone, super admins included, enters its password once. -->
      <section v-if="reviewGateVisible" class="prep-review-locked" aria-hidden="true">
        <Icon type="ios-locked-outline" />
      </section>
      <div v-else-if="isOverviewRoute" class="contest-overview-grid">
        <section class="contest-overview" aria-labelledby="contest-overview-title">
          <div class="section-heading">
            <span class="section-icon"><Icon type="file-text" /></span>
            <h2 id="contest-overview-title">{{$t('m.Overview')}}</h2>
          </div>
          <div v-if="contest.description" class="markdown-body contest-description" v-html="contest.description"></div>
          <p v-else class="contest-empty">{{$t('m.No_contest')}}</p>

        </section>

        <aside class="contest-guide" aria-labelledby="contest-guide-title">
          <div class="section-heading compact">
            <span class="section-icon"><Icon type="info-circle" /></span>
            <h2 id="contest-guide-title">{{$t('m.ContestType')}}</h2>
          </div>
          <dl>
            <div><dt>{{$t('m.Rule')}}</dt><dd :class="['contest-rule', ruleClass]">{{contest.rule_type || 'ACM'}}</dd></div>
            <div><dt>{{$t('m.ContestType')}}</dt><dd>{{contestTypeLabel}}</dd></div>
            <div><dt>{{$t('m.Problems')}}</dt><dd>{{contestProblemIds.length || '—'}}</dd></div>
            <div v-if="isPrepContest"><dt>{{$t('m.Status')}}</dt><dd><span :class="['contest-prep-badge', { 'is-review': reviewRunning }]">{{ reviewStatusLabel }}</span></dd></div>
            <div v-else><dt>{{$t('m.Status')}}</dt><dd :class="['contest-status', statusClass]">{{statusLabel}}</dd></div>
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

    <LegacyDialog :title="$t('m.Prep_Review_Password_Title')" width="420px" class="prep-gate-dialog"
                  :visible="reviewGateVisible" :close-on-click-modal="false" :close-on-press-escape="false"
                  :before-close="leaveReview" append-to-body>
      <p class="prep-dialog-note">{{ $t('m.Prep_Review_Password_Note') }}</p>
      <form class="gate-form" @submit.prevent="enterReview">
        <el-input ref="gateInput" v-model="reviewGatePassword" type="password" show-password maxlength="32"
                  :placeholder="$t('m.Contest_Password')"></el-input>
        <el-button type="primary" native-type="submit" :loading="enteringReview">{{ $t('m.Prep_Review_Password_Enter') }}</el-button>
      </form>
    </LegacyDialog>

    <LegacyDialog v-if="canManagePrep" :title="$t('m.Prep_Review')" width="480px"
                  :visible="reviewVisible" @update:visible="reviewVisible = $event">
      <p class="prep-dialog-note">{{ $t('m.Prep_Review_Note') }}</p>
      <p :class="['prep-dialog-count', { 'is-warning': selectionIssue }]">
        <Icon :type="selectionIssue ? 'alert-circle' : 'check-circle'" />
        <span>{{ selectionSummary }}</span>
      </p>
      <p v-if="reviewRunning" class="prep-dialog-running">
        <span class="prep-live"></span>{{ $t('m.Prep_Review_Running') }}
      </p>
      <el-form label-position="top" @submit.prevent>
        <el-form-item :label="$t('m.Contest_Password')">
          <el-input v-model="reviewPassword" maxlength="32" :placeholder="$t('m.Prep_Password_Placeholder')"></el-input>
          <small class="prep-field-hint">{{ $t('m.Prep_Review_Password_Hint') }}</small>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="prep-dialog-footer">
          <el-button v-if="reviewRunning" text @click="openReviewTab()">{{ $t('m.Prep_Review_Open_Current') }}</el-button>
          <el-button v-if="reviewRunning" text type="danger" :loading="endingReview" @click="endReview">{{ $t('m.Prep_Review_End') }}</el-button>
          <span class="prep-dialog-spacer"></span>
          <el-button @click="reviewVisible = false">{{ $t('m.Cancel') }}</el-button>
          <el-button type="primary" :loading="startingReview" :disabled="!uploadedCount" @click="startReview">
            {{ $t(reviewRunning ? 'm.Prep_Review_Restart' : 'm.Prep_Review_Start') }}
          </el-button>
        </div>
      </template>
    </LegacyDialog>

    <LegacyDialog v-if="canManagePrep" :title="$t('m.Prep_Publish')" width="560px"
                  :visible="publishVisible" @update:visible="publishVisible = $event">
      <p :class="['prep-dialog-count', { 'is-warning': publishBlocked }]">
        <Icon :type="publishBlocked ? 'alert-circle' : 'check-circle'" />
        <span>{{ selectionSummary }}</span>
      </p>
      <el-form label-position="top">
        <el-form-item :label="$t('m.Contest_Name')">
          <el-input v-model="publishForm.title" maxlength="128" :placeholder="$t('m.Contest_Name')"></el-input>
        </el-form-item>
        <el-form-item label="参赛账号">
          <el-switch v-model="publishForm.team_mode" inactive-text="原账号" active-text="批量队伍账号"></el-switch>
        </el-form-item>
        <div class="prep-publish-grid">
          <el-form-item :label="$t('m.Contest_Start_Time')">
            <el-date-picker v-model="publishForm.start_time" type="datetime"></el-date-picker>
          </el-form-item>
          <el-form-item :label="$t('m.Contest_End_Time')">
            <el-date-picker v-model="publishForm.end_time" type="datetime"></el-date-picker>
          </el-form-item>
          <el-form-item v-if="!publishForm.team_mode" :label="$t('m.Contest_Password')">
            <el-input v-model="publishForm.password" maxlength="32"></el-input>
          </el-form-item>
          <el-form-item :label="$t('m.Real_Time_Rank')">
            <el-switch v-model="publishForm.real_time_rank"></el-switch>
          </el-form-item>
          <el-form-item v-if="contest.rule_type === 'ACM'" label="封榜">
            <el-switch v-model="publishForm.freeze" @change="suggestFreeze"></el-switch>
          </el-form-item>
          <el-form-item v-if="contest.rule_type === 'ACM' && publishForm.freeze" label="封榜时间（赛后由管理员开榜）">
            <el-date-picker v-model="publishForm.rank_freeze_time" type="datetime"></el-date-picker>
          </el-form-item>
        </div>
        <el-form-item v-if="publishForm.team_mode" label="队伍信息" class="prep-publish-teams">
          <TeamRosterImport @update:teams="publishForm.teams = $event" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="publishVisible = false">{{ $t('m.Cancel') }}</el-button>
        <el-button type="primary" :loading="publishing" :disabled="publishBlocked || (publishForm.team_mode && !publishForm.teams.length)" @click="publish">{{ $t('m.Prep_Publish_Confirm') }}</el-button>
      </template>
    </LegacyDialog>

    <LegacyDialog v-if="canManagePrep" title="已发布" width="520px"
                  :visible="Boolean(publishResult)" @update:visible="publishResult = $event ? publishResult : null">
      <template v-if="publishResult">
        <p class="prep-published-copy">比赛链接（队伍用账号密码登录；比赛结束后无需登录即可查看）：</p>
        <div class="prep-published-link">
          <a :href="publishResult.link" target="_blank" rel="noopener">{{ publishResult.link }}</a>
          <el-button size="small" @click="copyText(publishResult.link)">复制</el-button>
        </div>
        <p class="prep-published-copy is-warning">{{ publishResult.teams.length }} 个队伍账号的密码只在这里给出一次，已自动下载 CSV。</p>
      </template>
      <template #footer>
        <el-button @click="downloadPublishedTeams">再次下载账号密码</el-button>
        <el-button type="primary" @click="publishResult = null">完成</el-button>
      </template>
    </LegacyDialog>

    <PrepStatementExportDialog v-if="prepRole" v-model:visible="exportVisible"
                               :contest-id="contestID" :contest-title="contest.title" />
  </div>
</template>

<script>
  import moment from 'moment'
  import { mapState, mapGetters, mapActions } from '@/store/compat'
  import { types } from '@/store'
  import api from '@oj/api'
  import { CONTEST_STATUS, CONTEST_STATUS_REVERSE, PREP_PLAN_CHANGED_EVENT, PUBLISH_DEFAULT_HOURS } from '@/utils/constants'
  import ContestAnnouncementBanner from '@oj/components/ContestAnnouncementBanner.vue'
  import TeamRosterImport from '@/shared/ui/TeamRosterImport.vue'
  import { downloadTeamAccounts } from '@/utils/teamRoster'
  import PrepStatementExportDialog from './PrepStatementExportDialog.vue'

  // The workspace tabs; every other contest route of a preparation contest is its review view.
  const PREP_CHANNEL = 'xju-oj-prep'
  const PREP_POLL_MS = 15000
  const PREP_SETTING_ROUTES = ['contest-details', 'contest-prep-problems', 'contest-prep-problem-edit',
    'contest-prep-upload', 'contest-prep-assign', 'contest-prep-roles']

  export default {
    name: 'ContestDetail',
    components: { ContestAnnouncementBanner, PrepStatementExportDialog, TeamRosterImport },
    data () {
      return {
        routeName: '',
        contestID: '',
        timer: null,
        reviewVisible: false,
        reviewPassword: '',
        startingReview: false,
        uploadedCount: null,
        myPlan: null,
        reviewGatePassword: '',
        enteringReview: false,
        // Whether the session's password access is known yet; until then the gate stays shut.
        accessKnown: false,
        endingReview: false,
        publishVisible: false,
        publishing: false,
        publishForm: {},
        // The team-account publish: its link and the one-time passwords.
        publishResult: null,
        exportVisible: false
      }
    },
    created () {
      this.prepPoll = null
      this.refreshingPrep = false
      this.prepChannel = typeof BroadcastChannel === 'function' ? new BroadcastChannel(PREP_CHANNEL) : null
      if (this.prepChannel) this.prepChannel.onmessage = this.onPrepMessage
    },
    mounted () {
      this.syncRoute()
      this.loadContest()
      window.addEventListener(PREP_PLAN_CHANGED_EVENT, this.onPlanChanged)
      document.addEventListener('visibilitychange', this.onPageVisible)
    },
    methods: {
      ...mapActions(['changeDomTitle']),
      syncRoute () {
        this.routeName = this.$route.name
        this.contestID = this.$route.params.contestID
      },
      loadContest () {
        this.accessKnown = false
        this.$store.dispatch('getContest').then(res => {
          this.accessKnown = true
          const data = res.data.data
          if (data.rule_type === 'AI') return this.$router.replace({ name: 'ai-contest', params: { contestID: data.id } })
          this.changeDomTitle({ title: data.title })
          this.syncClock()
          if (data.prep_state) {
            this.enterPrepWorkspace()
            this.loadMyPlan()
            this.startPrepSync()
          } else {
            this.stopPrepSync()
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
        return this.routeName === tab.name || (tab.activeNames || []).includes(this.routeName)
      },
      formatTime (value) {
        return value ? this.$filters.localtime(value, 'YYYY-MM-DD HH:mm') : '—'
      },
      syncClock () {
        // A review round has no countdown; only a published contest ticks.
        clearInterval(this.timer)
        this.timer = null
        if (this.isPrepContest) return
        if (moment(this.contest.end_time).isAfter(moment(this.now))) {
          this.timer = setInterval(() => this.$store.commit(types.NOW_ADD_1S), 1000)
        }
      },
      formatCountdown (seconds) {
        const duration = moment.duration(Math.max(seconds, 0), 'seconds')
        const days = Math.floor(duration.asDays())
        const clock = [Math.floor(duration.asHours()) % 24, duration.minutes(), duration.seconds()]
          .map(value => String(value).padStart(2, '0')).join(':')
        return days ? `${days}d ${clock}` : clock
      },
      enterPrepWorkspace () {
        // A preparation contest opens on its setting workspace; review lives at its own address.
        if (this.routeName === 'contest-details') {
          this.$router.replace({ name: 'contest-prep-problems', params: { contestID: this.contestID } })
        }
      },
      async loadSelection () {
        this.uploadedCount = null
        try {
          const res = await api.getPrepProblems(this.contestID)
          this.uploadedCount = res.data.data.length
        } catch (_) {
          this.uploadedCount = 0
        }
      },
      onPlanChanged (event) {
        this.loadMyPlan()
        // Tell the other tabs too, unless this event came from a refresh.
        if (!(event && event.detail && event.detail.remote)) this.notifyPrepChange()
      },
      async loadMyPlan () {
        if (!this.isPrepContest || !this.prepRole || !this.user.id) return
        const contestID = this.contestID
        try {
          const res = await api.getPrepPlan(contestID)
          if (contestID !== this.contestID) return
          const me = this.user.id
          const mine = res.data.data.progress.find(row => row.id === me)
          this.myPlan = {
            assigned: res.data.data.items.filter(item => item.assignee && item.assignee.id === me).length,
            uploaded: mine ? mine.uploaded : 0
          }
        } catch (_) {
          this.myPlan = null
        }
      },
      reviewHref () {
        return this.$router.resolve({ name: 'contest-prep-review', params: { contestID: this.contestID } }).href
      },
      // Open the tab while the click still counts as a user gesture, then point
      // it at the page once the request succeeds; popup blockers allow that.
      blankTab () {
        const tab = window.open('', '_blank')
        if (tab) tab.opener = null
        return tab
      },
      openReviewTab (tab = null) {
        const href = this.reviewHref()
        if (tab) tab.location.href = href
        else window.open(href, '_blank', 'noopener')
      },
      openReview () {
        if (!this.canManagePrep) return this.openReviewTab()
        this.reviewPassword = this.contest.password || ''
        this.reviewVisible = true
        this.loadSelection()
      },
      endReview () {
        this.$confirm(this.$t('m.Prep_Review_End_Confirm'), this.$t('m.Prep_Review_End'), {
          type: 'warning'
        }).then(async () => {
          this.endingReview = true
          try {
            await api.endPrepReview(this.contestID)
            await this.$store.dispatch('getContest')
            this.syncClock()
            this.notifyPrepChange()
            this.reviewVisible = false
            this.$success(this.$t('m.Prep_Review_Ended_Done'))
          } catch (_) {
            // The API client already shows the error.
          } finally {
            this.endingReview = false
          }
        }).catch(() => {})
      },
      // Only the close button gets here; the gate also closes by itself once the password is in.
      leaveReview () {
        this.$router.push({ name: 'contest-prep-problems', params: { contestID: this.contestID } })
      },
      // Hot update: review rounds, the password and the plan change in other tabs and
      // on other people's screens, so preparation contests refresh themselves.
      notifyPrepChange () {
        if (this.prepChannel) this.prepChannel.postMessage({ contestID: String(this.contestID) })
      },
      onPrepMessage (event) {
        if (event.data && event.data.contestID === String(this.contestID)) this.refreshPrep()
      },
      onPageVisible () {
        if (document.visibilityState === 'visible') this.refreshPrep()
      },
      async refreshPrep () {
        if (!this.isPrepContest || this.refreshingPrep || String(this.contest.id) !== String(this.contestID)) return
        this.refreshingPrep = true
        try {
          await this.$store.dispatch('getContest')
          this.syncClock()
          // Reloads the plan board and this member's progress without echoing to other tabs.
          window.dispatchEvent(new CustomEvent(PREP_PLAN_CHANGED_EVENT, { detail: { remote: true } }))
        } catch (_) {
          // A transient failure; the next tick tries again.
        } finally {
          this.refreshingPrep = false
        }
      },
      startPrepSync () {
        this.stopPrepSync()
        this.prepPoll = setInterval(() => {
          if (document.visibilityState === 'visible') this.refreshPrep()
        }, PREP_POLL_MS)
      },
      stopPrepSync () {
        clearInterval(this.prepPoll)
        this.prepPoll = null
      },
      async enterReview () {
        const password = this.reviewGatePassword.trim()
        if (!password) return this.$error(this.$t('m.Contest_Password_Required'))
        this.enteringReview = true
        try {
          await api.checkContestPassword(this.contestID, password)
          this.reviewGatePassword = ''
          this.$store.commit(types.CONTEST_ACCESS, { access: true })
        } catch (_) {
          // The API client already shows the error.
        } finally {
          this.enteringReview = false
        }
      },
      async startReview () {
        const tab = this.blankTab()
        const password = this.reviewPassword.trim()
        this.startingReview = true
        try {
          await api.startPrepReview(this.contestID, password)
          await this.$store.dispatch('getContest')
          this.notifyPrepChange()
          this.syncClock()
          this.reviewVisible = false
          this.openReviewTab(tab)
        } catch (_) {
          // The API client already shows the error.
          if (tab) tab.close()
        } finally {
          this.startingReview = false
        }
      },
      openExport () {
        this.exportVisible = true
      },
      openPublish () {
        // The contest window is set here; keep a future one, otherwise
        // suggest tomorrow 09:00 for the usual five hours.
        let start = moment(this.contest.start_time)
        let end = moment(this.contest.end_time)
        if (!start.isAfter(moment(this.now))) {
          start = moment(this.now).add(1, 'day').startOf('day').hour(9)
          end = start.clone().add(PUBLISH_DEFAULT_HOURS, 'hours')
        }
        this.publishForm = {
          title: this.contest.title,
          start_time: start.toDate(),
          end_time: end.toDate(),
          // The published contest's password is chosen here; the review password is not carried over.
          password: '',
          real_time_rank: this.contest.real_time_rank !== false,
          team_mode: false,
          teams: [],
          freeze: false,
          rank_freeze_time: null
        }
        this.publishVisible = true
        this.loadSelection()
      },
      suggestFreeze (on) {
        // The usual board freezes four hours in, or an hour before a shorter contest ends.
        if (!on || this.publishForm.rank_freeze_time) return
        const start = moment(this.publishForm.start_time)
        const end = moment(this.publishForm.end_time)
        let freeze = start.clone().add(4, 'hours')
        if (!freeze.isBefore(end)) freeze = moment.max(start.clone().add(1, 'minute'), end.clone().subtract(1, 'hour'))
        this.publishForm.rank_freeze_time = freeze.toDate()
      },
      async teamLogout () {
        try { await api.logout() } catch (_) {}
        this.$store.dispatch('clearProfile')
        this.$router.replace({ name: 'contest-arena', params: { contestID: this.contestID } })
      },
      copyText (text) {
        navigator.clipboard.writeText(text).then(() => this.$success('已复制'), () => this.$error('复制失败，请手动选择链接'))
      },
      downloadPublishedTeams () {
        const result = this.publishResult
        if (result) downloadTeamAccounts(`contest-${result.id}-teams.csv`, result.teams)
      },
      async publish () {
        const form = this.publishForm
        if (new Date(form.end_time) <= new Date(form.start_time)) {
          this.$error(this.$t('m.Prep_Time_Invalid'))
          return
        }
        const freeze = this.contest.rule_type === 'ACM' && form.freeze && form.rank_freeze_time
        if (freeze && !(new Date(form.start_time) < new Date(form.rank_freeze_time) && new Date(form.rank_freeze_time) < new Date(form.end_time))) {
          this.$error('封榜时间须在比赛开始和结束之间')
          return
        }
        // A team publish stays here to hand over the link and the passwords.
        const tab = form.team_mode ? null : this.blankTab()
        this.publishing = true
        try {
          const res = await api.publishPrepContest({
            contest_id: this.contestID,
            title: form.title,
            start_time: new Date(form.start_time).toISOString(),
            end_time: new Date(form.end_time).toISOString(),
            password: form.team_mode ? '' : form.password,
            real_time_rank: form.real_time_rank,
            rank_freeze_time: freeze ? new Date(form.rank_freeze_time).toISOString() : null,
            ...(form.team_mode ? { teams: form.teams } : {})
          })
          this.publishVisible = false
          this.$success(this.$t('m.Prep_Published'))
          const published = res.data.data
          if (form.team_mode) {
            const link = new URL(this.$router.resolve({ name: 'contest-arena', params: { contestID: published.id } }).href, window.location.origin).href
            this.publishResult = { id: published.id, link, teams: published.teams }
            this.downloadPublishedTeams()
          } else {
            const href = this.$router.resolve({ name: 'contest-details', params: { contestID: published.id } }).href
            if (tab) tab.location.href = href
            else window.open(href, '_blank', 'noopener')
          }
          // Show the new "published as" link on this page.
          this.$store.dispatch('getContest').catch(() => {})
          this.notifyPrepChange()
        } catch (_) {
          // The API client already shows the error.
          if (tab) tab.close()
        } finally {
          this.publishing = false
        }
      }
    },
    computed: {
      ...mapState({
        contest: state => state.contest.contest,
        contestAccess: state => state.contest.access,
        now: state => state.contest.now
      }),
      ...mapGetters([
        'contestMenuDisabled', 'contestRuleType', 'contestStatus', 'isContestAdmin',
        'isAuthenticated', 'OIContestRealTimePermission',
        'isPrepContest', 'prepRole', 'canManagePrep', 'user'
      ]),
      publishedContests () {
        return this.contest.published_contests || []
      },
      myTeam () {
        const team = this.$store.state.user.profile.team
        return team && String(team.contest_id) === String(this.contestID) ? team : null
      },
      isPrepSettingView () {
        return this.isPrepContest && PREP_SETTING_ROUTES.includes(this.routeName)
      },
      isPrepReviewView () {
        return this.isPrepContest && !this.isPrepSettingView
      },
      reviewGateVisible () {
        // Problem pages stay open: organizers reach them from the setting list too.
        return this.accessKnown && this.isPrepReviewView && !this.isProblemRoute && String(this.contest.id) === String(this.contestID) &&
          this.contest.contest_type && this.contest.contest_type !== 'Public' && !this.contestAccess
      },
      isOverviewRoute () {
        return this.routeName === 'contest-details' || this.routeName === 'contest-prep-review'
      },
      prepStateLabel () {
        return this.$t(this.isPrepReviewView ? 'm.Prep_State_Review' : 'm.Prep_State_Preparation')
      },
      problemCount () {
        return this.contest.prep_problem_count || null
      },
      selectionIssue () {
        return this.uploadedCount !== null && (!this.uploadedCount || (this.problemCount && this.uploadedCount !== this.problemCount))
      },
      publishBlocked () {
        return this.uploadedCount === null || !this.uploadedCount || Boolean(this.problemCount && this.uploadedCount !== this.problemCount)
      },
      selectionSummary () {
        if (this.uploadedCount === null) return this.$t('m.Loading')
        if (!this.uploadedCount) return this.$t('m.Prep_No_Uploads')
        if (this.problemCount) return this.$t('m.Prep_Uploaded_Of', { uploaded: this.uploadedCount, total: this.problemCount })
        return this.$t('m.Prep_Uploaded_Count', { uploaded: this.uploadedCount })
      },
      myProgressPercent () {
        if (!this.myPlan || !this.myPlan.assigned) return 0
        return Math.min(this.myPlan.uploaded / this.myPlan.assigned, 1) * 100
      },
      metaStart () {
        if (!this.isPrepContest) return this.contest.start_time
        return this.isPrepReviewView ? this.contest.review_started_at : this.contest.create_time
      },
      metaEnd () {
        if (!this.isPrepContest) return this.contest.end_time
        return this.isPrepReviewView && this.reviewEndsAt ? this.reviewEndsAt.toDate() : null
      },
      canReadAnnouncements () {
        if (!this.isAuthenticated || !this.contestID || String(this.contest.id) !== String(this.contestID)) return false
        if (this.isPrepContest) return true
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
        if (this.isPrepSettingView) {
          return [
            { name: 'contest-prep-problems', label: 'Prep_Problem_List', icon: 'list-ol', route: { name: 'contest-prep-problems', params: common }, activeNames: ['contest-prep-problem-edit'] },
            { name: 'contest-prep-upload', label: 'Prep_Upload', icon: 'upload', route: { name: 'contest-prep-upload', params: common } },
            { name: 'contest-prep-assign', label: 'Prep_Assign', icon: 'check-square', route: { name: 'contest-prep-assign', params: common } },
            { name: 'contest-prep-roles', label: 'Prep_Roles', icon: 'users', route: { name: 'contest-prep-roles', params: common } }
          ]
        }
        // A review round uses the same tabs as a published contest.
        const overview = this.isPrepContest ? 'contest-prep-review' : 'contest-details'
        return [
          { name: overview, label: 'Overview', icon: 'home', route: { name: overview, params: common } },
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
      reviewEndsAt () {
        // A review round has no time limit; only the creator ends it.
        if (!this.isPrepContest || !this.contest.review_started_at) return null
        return this.contest.review_ended_at ? moment(this.contest.review_ended_at) : null
      },
      reviewRunning () {
        return Boolean(this.isPrepContest && this.contest.review_started_at && !this.contest.review_ended_at)
      },
      reviewStatusLabel () {
        if (this.reviewRunning) return this.$t('m.Prep_State_Review')
        return this.$t(this.contest.review_started_at ? 'm.Prep_Review_Ended' : 'm.Prep_Review_Not_Started')
      },
      countdownCaption () {
        if (this.isPrepContest) {
          if (this.reviewRunning) return this.$t('m.Prep_State_Review')
          return this.$t(this.contest.review_started_at ? 'm.Prep_Review_Ended' : 'm.Prep_Review_Not_Started')
        }
        if (this.contestStatus === CONTEST_STATUS.NOT_START) return this.$t('m.Not_Started')
        if (this.contestStatus === CONTEST_STATUS.ENDED) return this.$t('m.Ended')
        return this.$t('m.Underway')
      },
      countdownValue () {
        if (this.isPrepContest) {
          return this.reviewRunning ? this.$t('m.Prep_Review_Unlimited') : '—'
        }
        if (this.contestStatus === CONTEST_STATUS.ENDED) return this.$t('m.Ended')
        const target = this.contestStatus === CONTEST_STATUS.NOT_START ? this.contest.start_time : this.contest.end_time
        if (!target) return '—'
        return this.formatCountdown(moment(target).diff(this.now, 'seconds'))
      },
      durationLabel () {
        if (this.isPrepContest) {
          return this.isPrepReviewView && this.contest.review_started_at ? this.$t('m.Prep_Review_Unlimited') : '—'
        }
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
      reviewGateVisible (visible) {
        if (visible) this.$nextTick(() => this.$refs.gateInput && this.$refs.gateInput.focus())
      },
      '$route' (route, previous) {
        const contestChanged = String(route.params.contestID || '') !== String(previous.params.contestID || '')
        this.syncRoute()
        if (contestChanged) this.loadContest()
        else this.changeDomTitle({ title: this.contest.title })
        if (!contestChanged && this.isPrepContest) {
          this.enterPrepWorkspace()
          // Uploads and deletions happen on other tabs; refresh the member's own progress.
          if (this.isPrepSettingView) this.loadMyPlan()
        }
      }
    },
    beforeUnmount () {
      window.removeEventListener(PREP_PLAN_CHANGED_EVENT, this.onPlanChanged)
      document.removeEventListener('visibilitychange', this.onPageVisible)
      this.stopPrepSync()
      if (this.prepChannel) this.prepChannel.close()
      clearInterval(this.timer)
      this.$store.commit(types.CLEAR_CONTEST)
    }
  }
</script>

<style scoped lang="less">
@import "@/styles/contest-detail.less";

/* Preparation chips follow the Notion-style tags used across the site. */
.contest-prep-badge,
.contest-prep-role,
.contest-prep-published {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.contest-prep-badge { background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
.contest-prep-badge.is-review { background: var(--tag-tools-bg); color: var(--cat-tools); }
.contest-prep-role { background: rgba(55, 53, 47, .07); color: var(--color-text-muted); }
.contest-prep-published { background: rgba(55, 53, 47, .04); color: var(--color-link); }
.contest-prep-published:hover { background: rgba(35, 131, 226, .1); color: var(--color-link); }

.prep-controls {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.prep-action,
.prep-back {
  display: inline-flex;
  height: 30px;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--color-text);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color var(--transition), border-color var(--transition), color var(--transition);
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 15px; height: 15px; }
  &:hover, &:focus-visible { border-color: var(--line-strong); background: var(--bg-hover); color: var(--color-text); }
}
.prep-back { border-color: transparent; color: var(--color-text-muted); font-weight: 500; }
.prep-action.is-danger { color: var(--oj-danger); &:hover, &:focus-visible { border-color: rgba(224, 62, 62, .35); background: var(--tag-research-bg); color: var(--oj-danger); } }
/* A soft pulse marks a review round that is still running. */
.prep-live {
  position: relative;
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: var(--cat-tools);
  &::after {
    position: absolute;
    inset: -3px;
    border-radius: 50%;
    background: currentColor;
    color: var(--cat-tools);
    content: "";
    opacity: .25;
    animation: prep-live 1.8s ease-out infinite;
  }
}
@keyframes prep-live {
  from { transform: scale(.6); opacity: .35; }
  to { transform: scale(1.6); opacity: 0; }
}
.prep-publish {
  height: 30px;
  padding: 0 14px;
  border: 0;
  border-radius: 6px;
  background: var(--color-link);
  color: #fff;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color var(--transition);
  &:hover, &:focus-visible { background: #0b6bcb; }
}
.prep-settings {
  display: inline-flex;
  width: 30px;
  height: 30px;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: var(--color-text-muted);
  transition: background-color var(--transition), color var(--transition);
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 16px; height: 16px; }
  &:hover, &:focus-visible { background: rgba(55, 53, 47, .06); color: var(--color-text); }
}
@media (max-width: 760px) {
  .prep-controls { width: 100%; margin-left: 0; justify-content: flex-end; }
}
.prep-review-locked {
  display: flex;
  min-height: 220px;
  align-items: center;
  justify-content: center;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-faint);
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 28px; height: 28px; }
}
.gate-form { display: flex; width: 100%; gap: 8px; }
.gate-form .el-button { margin-left: 0; }
.prep-my-progress {
  display: flex;
  width: fit-content;
  align-items: center;
  gap: 10px;
  margin: 0 0 10px auto;
  padding: 5px 12px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-bg);
  color: var(--color-text-muted);
  font-size: 12px;
  strong { color: var(--color-text); font-variant-numeric: tabular-nums; }
  &.is-done strong { color: var(--cat-tools); }
}
.my-progress-track {
  position: relative;
  width: 120px;
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(55, 53, 47, .08);
}
.my-progress-fill {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: inherit;
  background: var(--color-link);
  transition: width .45s cubic-bezier(.2, .8, .2, 1);
}
.prep-my-progress.is-done .my-progress-fill { background: var(--cat-tools); }
.prep-dialog-note { margin: 0 0 12px; color: var(--color-text-muted); font-size: 13px; line-height: 1.6; }
.prep-dialog-count {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  padding: 9px 12px;
  border-radius: 8px;
  background: var(--tag-tools-bg);
  color: var(--cat-tools);
  font-size: 13px;
  font-weight: 600;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 16px; height: 16px; }
  &.is-warning { background: var(--tag-course-bg); color: var(--oj-warning); }
}
.prep-dialog-running {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: -4px 0 14px;
  color: var(--color-text-muted);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.prep-field-hint { display: block; margin-top: 4px; color: var(--color-text-faint); font-size: 12px; line-height: 1.5; }
.prep-dialog-footer { display: flex; align-items: center; gap: 8px; }
.prep-dialog-footer .el-button + .el-button { margin-left: 0; }
.prep-dialog-spacer { flex: 1; }
@media (prefers-reduced-motion: reduce) {
  .prep-live::after { animation: none; }
}
.prep-publish-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
.prep-publish-teams :deep(.el-form-item__content) { display: block; }
.contest-team { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; color: var(--color-text); font-size: 13px; cursor: default; }
.contest-team strong { font-weight: 650; }
.contest-team button { margin-left: 6px; padding: 0; border: 0; background: none; color: var(--color-text-muted); font: inherit; font-size: 12px; cursor: pointer; }
.contest-team button:hover { color: var(--color-text); }
.prep-published-copy { margin: 0 0 8px; color: var(--color-text-muted); font-size: 13px; line-height: 1.6; }
.prep-published-copy.is-warning { margin-top: 12px; color: var(--color-text); font-weight: 600; }
.prep-published-link { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg-subtle); }
.prep-published-link a { min-width: 0; flex: 1; font: 13px var(--font-mono); overflow-wrap: anywhere; }
.prep-publish-grid :deep(.el-date-editor.el-input) { width: 100%; }
@media (max-width: 560px) {
  .prep-publish-grid { grid-template-columns: 1fr; }
}
</style>
