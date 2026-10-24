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
                  <template v-if="isPrepContest">
                    <span :class="['contest-prep-badge', { 'is-review': isPrepReview }]">{{ prepStateLabel }}</span>
                    <span v-if="prepRole" :class="['contest-prep-role', `is-${prepRole.toLowerCase()}`]">{{ $t(`m.Prep_Role_${prepRole}`) }}</span>
                    <router-link v-for="item in publishedContests" :key="item.id" class="contest-prep-published"
                                 :to="{ name: 'contest-details', params: { contestID: item.id } }"
                                 :title="item.title">{{ $t('m.Prep_Published_As') }} #{{ item.id }}</router-link>
                  </template>
                  <span v-else :class="['contest-status', statusClass]">{{statusLabel}}</span>
                  <span v-if="contest.contest_type && contest.contest_type !== 'Public' && !contestEnded" class="contest-private">
                    <Icon type="ios-locked-outline" />
                    {{contestTypeLabel}}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="!isPrepContest" class="contest-countdown" :aria-label="countdownCaption">
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
        <div v-if="canManagePrep" class="prep-controls">
          <div class="prep-mode-switch" role="group" :aria-label="$t('m.Contest_Preparation')">
            <button v-for="state in prepStates" :key="state" type="button"
                    :class="{ 'is-active': contest.prep_state === state }"
                    :disabled="switchingState"
                    :aria-pressed="contest.prep_state === state ? 'true' : 'false'"
                    @click="switchPrepState(state)">{{ $t(`m.Prep_Mode_${state}`) }}</button>
          </div>
          <button type="button" class="prep-publish" @click="openPublish">{{ $t('m.Prep_Publish') }}</button>
          <el-tooltip :content="$t('m.Prep_Edit_Settings')" placement="top">
            <a class="prep-settings" :href="`/admin/contest/${contestID}/edit`" :aria-label="$t('m.Prep_Edit_Settings')">
              <Icon type="settings" />
            </a>
          </el-tooltip>
        </div>
      </nav>
    </template>

    <main :class="['contest-content', { 'is-root': routeName === 'contest-details' }]">
      <div v-if="routeName === 'contest-details'" class="contest-overview-grid">
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
      <el-form label-position="top">
        <el-form-item :label="$t('m.Contest_Name')">
          <el-input v-model="publishForm.title" maxlength="128" :placeholder="$t('m.Contest_Name')"></el-input>
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

  const PREP_STATES = ['Preparation', 'Review']

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
          if (data.prep_state) return this.enterPrepTab()
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
      enterPrepTab () {
        // Preparation contests have no overview page.
        const names = this.visibleTabs.flatMap(tab => [tab.name, ...(tab.activeNames || [])])
        if (!names.includes(this.routeName) && this.routeName !== 'contest-problem-details') {
          this.$router.replace(this.visibleTabs[0].route)
        }
      },
      async switchPrepState (state) {
        if (state === this.contest.prep_state) return
        this.switchingState = true
        try {
          await api.setPrepContestState(this.contestID, state)
          await this.$store.dispatch('getContest')
          this.enterPrepTab()
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
        'isPrepContest', 'isPrepReview', 'prepRole', 'canManagePrep', 'canAuthorPrep', 'canEditPrep'
      ]),
      publishedContests () {
        return this.contest.published_contests || []
      },
      prepStateLabel () {
        return this.$t(this.isPrepReview ? 'm.Prep_State_Review' : 'm.Prep_State_Preparation')
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
        if (this.isPrepContest && this.isPrepReview) {
          // Review runs like a real contest, without announcements.
          return [
            { name: 'contest-problem-list', label: 'Problems', icon: 'ios-photos', route: { name: 'contest-problem-list', params: common } },
            { name: 'contest-submission-list', label: 'Submissions', icon: 'navicon-round', route: { name: 'contest-submission-list', params: common } },
            { name: 'contest-rank', label: 'Rankings', icon: 'stats-bars', route: { name: 'contest-rank', params: common } }
          ]
        }
        if (this.isPrepContest) {
          const list = this.canAuthorPrep ? 'contest-prep-problems' : 'contest-problem-list'
          return [
            { name: list, label: 'Prep_Problem_List', icon: 'list-ol', route: { name: list, params: common }, activeNames: ['contest-prep-problem-edit'] },
            { name: 'contest-prep-upload', label: 'Prep_Upload', icon: 'upload', route: { name: 'contest-prep-upload', params: common }, visible: this.canAuthorPrep },
            { name: 'contest-prep-roles', label: 'Prep_Roles', icon: 'users', route: { name: 'contest-prep-roles', params: common } }
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
        if (!contestChanged && this.isPrepContest && this.routeName === 'contest-details') this.enterPrepTab()
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
.prep-mode-switch {
  display: inline-flex;
  padding: 2px;
  border-radius: 6px;
  background: rgba(55, 53, 47, .06);
  button {
    height: 26px;
    padding: 0 12px;
    border: 0;
    border-radius: 4px;
    background: transparent;
    color: var(--color-text-muted);
    font: inherit;
    font-size: 13px;
    cursor: pointer;
    transition: background-color var(--transition), color var(--transition), box-shadow var(--transition);
    &:hover:not(.is-active) { color: var(--color-text); }
    &.is-active {
      background: var(--color-bg);
      color: var(--color-text);
      font-weight: 600;
      box-shadow: 0 0 0 1px rgba(15, 15, 15, .06), 0 1px 2px rgba(15, 15, 15, .1);
    }
    &:disabled { cursor: wait; }
  }
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
.prep-publish-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
.prep-publish-grid :deep(.el-date-editor.el-input) { width: 100%; }
@media (max-width: 560px) {
  .prep-publish-grid { grid-template-columns: 1fr; }
}
</style>
