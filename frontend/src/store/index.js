import { createPinia, defineStore } from 'pinia'
import api from '@oj/api'
import moment from 'moment'
import storage from '@/utils/storage'
import i18n from '@/i18n'
import types from './types'
import { STORAGE_KEY, USER_TYPE, PROBLEM_PERMISSION, CONTEST_STATUS, CONTEST_TYPE } from '@/utils/constants'
import runtime from '@/utils/runtime'
import { cloneFixtures, MOCK_CONTESTS, MOCK_PROBLEMS } from '@oj/mocks/fixtures'

let activeRouter = null
export const setStoreRouter = router => { activeRouter = router }
const route = () => activeRouter ? activeRouter.currentRoute.value : { params: {}, meta: {} }
let contestEpoch = 0
const contestRequests = {}
const contestRequestGuard = lane => {
  const id = String(route().params.contestID || '')
  const epoch = contestEpoch
  const generation = (contestRequests[lane] || 0) + 1
  contestRequests[lane] = generation
  return () => epoch === contestEpoch && generation === contestRequests[lane] &&
    id === String(route().params.contestID || '')
}

const useApplicationStore = defineStore('application', {
  state: () => ({
    website: {},
    authProviders: {
      authentik: {
        // In local frontend dev mode the Authentik-styled entry remains
        // visible, but its click handler uses the local admin quick login.
        enabled: runtime.AUTHENTIK_OIDC_ENABLED || runtime.OJ_FRONTEND_DEV_MODE,
        login_url: '/api/auth/oidc/login/?next=/',
        register_url: runtime.AUTHENTIK_OIDC_REGISTER_URL,
        link_url: '/api/auth/oidc/link/?next=/setting/security',
        linked: false
      },
      local: {
        login_enabled: runtime.AUTHENTIK_LOCAL_LOGIN_ENABLED,
        register_enabled: runtime.AUTHENTIK_LOCAL_REGISTER_ENABLED
      }
    },
    modalStatus: { mode: 'login', visible: false },
    user: { profile: {} },
    contest: {
      now: moment(), access: false, rankLimit: 10, forceUpdate: false,
      contest: { created_by: {}, contest_type: CONTEST_TYPE.PUBLIC },
      contestProblems: [], itemVisible: { menu: true, chart: false, realName: false }
    }
  }),
  getters: {
    profile: state => state.user.profile,
    currentUser: state => state.user.profile.user || {},
    isAuthenticated () { return !!this.currentUser.id },
    isAdminRole () { return this.currentUser.admin_type === USER_TYPE.ADMIN || this.currentUser.admin_type === USER_TYPE.SUPER_ADMIN },
    isSuperAdmin () { return this.currentUser.admin_type === USER_TYPE.SUPER_ADMIN },
    hasProblemPermission () { return this.currentUser.problem_permission !== PROBLEM_PERMISSION.NONE },
    contestLoaded: state => !!state.contest.contest.status,
    contestStatus () {
      if (!this.contestLoaded) return null
      if (moment(this.contest.contest.start_time) > this.contest.now) return CONTEST_STATUS.NOT_START
      if (moment(this.contest.contest.end_time) < this.contest.now) return CONTEST_STATUS.ENDED
      return CONTEST_STATUS.UNDERWAY
    },
    contestRuleType: state => state.contest.contest.rule_type || null,
    isContestRegistered () { return this.isContestAdmin || this.contest.contest.registered === true },
    isContestAdmin () { return this.isAuthenticated && (this.contest.contest.created_by.id === this.currentUser.id || this.currentUser.admin_type === USER_TYPE.SUPER_ADMIN) },
    contestMenuDisabled () {
      // An ended contest is public practice material: announcements,
      // submissions and rankings stay readable without registration or the
      // contest password.
      if (this.contestStatus === CONTEST_STATUS.ENDED) return false
      if (this.isContestRegistered) return false
      return this.contest.contest.contest_type === CONTEST_TYPE.PUBLIC ? this.contestStatus === CONTEST_STATUS.NOT_START : !this.contest.access
    },
    OIContestRealTimePermission () { return this.contestRuleType === 'ACM' || this.contestStatus === CONTEST_STATUS.ENDED || this.contest.contest.real_time_rank === true || this.isContestAdmin },
    problemSubmitDisabled () {
      if (!this.isAuthenticated) return true
      if (!route().params.contestID) return false
      if (!this.contestLoaded || String(this.contest.contest.id) !== String(route().params.contestID)) return true
      if (this.contestStatus === CONTEST_STATUS.NOT_START) return !this.isContestAdmin
      return false
    },
    passwordFormVisible () { return this.contestStatus !== CONTEST_STATUS.ENDED && this.contest.contest.contest_type !== CONTEST_TYPE.PUBLIC && !this.contest.access && !this.isContestAdmin },
    contestStartTime: state => moment(state.contest.contest.start_time),
    contestEndTime: state => moment(state.contest.contest.end_time),
    countdown () {
      if (this.contestStatus === CONTEST_STATUS.ENDED) return 'Ended'
      const end = this.contestStatus === CONTEST_STATUS.NOT_START ? this.contestStartTime : this.contestEndTime
      const duration = moment.duration(end.diff(this.contest.now, 'seconds'), 'seconds')
      if (this.contestStatus === CONTEST_STATUS.NOT_START && duration.weeks() > 0) return 'Start At ' + duration.humanize()
      return '-' + [Math.floor(duration.asHours()), duration.minutes(), duration.seconds()].join(':')
    }
  },
  actions: {
    async getWebsiteConfig () { const res = await api.getWebsiteConf(); this.website = res.data.data },
    async getAuthProviders () {
      if (runtime.OJ_FRONTEND_DEV_MODE) return
      try {
        const res = await api.getAuthProviders()
        if (res.data.data) this.authProviders = res.data.data
      } catch (_) {
        // Keep the safe runtime defaults if the backend is unavailable or older.
      }
    },
    changeModalStatus ({ mode, visible }) { if (mode !== undefined) this.modalStatus.mode = mode; if (visible !== undefined) this.modalStatus.visible = visible },
    changeDomTitle (payload) {
      const title = payload && payload.title ? payload.title : route().meta.title
      window.document.title = `XJU-OJ | ${title || 'Home'}`
    },
    async getProfile () {
      const res = await api.getUserInfo()
      const profile = res.data.data || {}
      this.changeProfile(profile)
      if (profile.oj_onboarding_completed === false && route().name !== 'profile-setting') {
        activeRouter && activeRouter.push({ name: 'profile-setting', query: { onboarding: '1' } })
      }
    },
    clearProfile () { this.changeProfile({}); storage.clear() },
    changeProfile (profile) {
      this.user.profile = profile
      if (profile.language) i18n.global.locale.value = profile.language
      storage.set(STORAGE_KEY.AUTHED, !!profile.user)
    },
    async getContest () {
      const current = contestRequestGuard('details')
      const mockContest = import.meta.env.DEV && MOCK_CONTESTS.find(contest => String(contest.id) === String(route().params.contestID))
      if (mockContest) {
        const contest = cloneFixtures([mockContest])[0]
        this.contest.contest = contest
        this.contest.now = moment(contest.now)
        return { data: { data: contest } }
      }
      try {
        const res = await api.getContest(route().params.contestID)
        if (!current()) return res
        this.contest.contest = res.data.data
        this.contest.now = moment(res.data.data.now)
        if (this.contest.contest.contest_type === CONTEST_TYPE.PRIVATE) await this.getContestAccess()
        return res
      } catch (error) {
        if (!current()) return
        const mock = MOCK_CONTESTS.find(contest => String(contest.id) === String(route().params.contestID))
        if (!mock) throw error
        const contest = cloneFixtures([mock])[0]
        this.contest.contest = contest
        this.contest.now = moment(contest.now)
        return { data: { data: contest } }
      }
    },
    async getContestProblems () {
      const current = contestRequestGuard('problems')
      const mockContest = import.meta.env.DEV && MOCK_CONTESTS.find(contest => String(contest.id) === String(route().params.contestID))
      if (mockContest) {
        const result = cloneFixtures(mockContest.problem_ids
          .map(id => MOCK_PROBLEMS.find(problem => String(problem._id) === String(id)))
          .filter(Boolean))
        this.contest.contestProblems = result
        return { data: { data: result } }
      }
      try {
        const res = await api.getContestProblemList(route().params.contestID)
        if (!current()) return res
        const problems = Array.isArray(res.data.data) ? res.data.data : []
        const mock = MOCK_CONTESTS.find(contest => String(contest.id) === String(route().params.contestID))
        const selected = mock && mock.problem_ids
          ? mock.problem_ids.map(id => MOCK_PROBLEMS.find(problem => String(problem._id) === String(id))).filter(Boolean)
          : []
        const result = problems.length ? problems : (selected.length ? cloneFixtures(selected) : problems)
        this.contest.contestProblems = result.sort((a, b) => a._id === b._id ? 0 : (a._id > b._id ? 1 : -1))
        return { data: { data: result } }
      } catch (error) {
        if (!current()) return
        const mock = MOCK_CONTESTS.find(contest => String(contest.id) === String(route().params.contestID))
        if (!mock) {
          this.contest.contestProblems = []
          throw error
        }
        const selected = mock.problem_ids
          .map(id => MOCK_PROBLEMS.find(problem => String(problem._id) === String(id)))
          .filter(Boolean)
        const result = cloneFixtures(selected)
        this.contest.contestProblems = result
        return { data: { data: result } }
      }
    },
    async getContestAccess () {
      const current = contestRequestGuard('access')
      const res = await api.getContestAccess(route().params.contestID)
      if (current()) this.contest.access = res.data.data.access
      return res
    },
    async registerContest ({ password = '' } = {}) {
      const current = contestRequestGuard('registration')
      const res = await api.registerContest(route().params.contestID, password)
      if (!current()) return res
      this.contest.contest.registered = true
      this.contest.access = true
      return res
    }
  }
})

const pinia = createPinia()
let store
const ensureStore = () => store || (store = useApplicationStore(pinia))

const getterMap = {
  website: s => s.website, authProviders: s => s.authProviders, modalStatus: s => s.modalStatus, user: s => s.currentUser, profile: s => s.profile,
  isAuthenticated: s => s.isAuthenticated, isAdminRole: s => s.isAdminRole, isSuperAdmin: s => s.isSuperAdmin,
  hasProblemPermission: s => s.hasProblemPermission, contestLoaded: s => s.contestLoaded, contestStatus: s => s.contestStatus,
  contestRuleType: s => s.contestRuleType, isContestAdmin: s => s.isContestAdmin, isContestRegistered: s => s.isContestRegistered, contestMenuDisabled: s => s.contestMenuDisabled,
  OIContestRealTimePermission: s => s.OIContestRealTimePermission, problemSubmitDisabled: s => s.problemSubmitDisabled,
  passwordFormVisible: s => s.passwordFormVisible, contestStartTime: s => s.contestStartTime, contestEndTime: s => s.contestEndTime,
  countdown: s => s.countdown
}

const facade = {
  install (app) { app.use(pinia); store = useApplicationStore(pinia); app.config.globalProperties.$store = facade },
  get state () { return ensureStore().$state },
  get getters () { return new Proxy({}, { get: (_, key) => getterMap[key] ? getterMap[key](ensureStore()) : undefined }) },
  dispatch (name, payload) { const target = ensureStore()[name]; return typeof target === 'function' ? target.call(ensureStore(), payload) : Promise.reject(new Error(`Unknown action ${name}`)) },
  commit (type, payload = {}) {
    const s = ensureStore()
    const handlers = {
      [types.UPDATE_WEBSITE_CONF]: () => { s.website = payload.websiteConfig },
      [types.CHANGE_MODAL_STATUS]: () => s.changeModalStatus(payload),
      [types.CHANGE_PROFILE]: () => s.changeProfile(payload.profile),
      [types.CHANGE_CONTEST]: () => { s.contest.contest = payload.contest },
      [types.CHANGE_CONTEST_ITEM_VISIBLE]: () => { s.contest.itemVisible = { ...s.contest.itemVisible, ...payload } },
      [types.CHANGE_RANK_FORCE_UPDATE]: () => { s.contest.forceUpdate = payload.value },
      [types.CHANGE_CONTEST_PROBLEMS]: () => { s.contest.contestProblems = payload.contestProblems },
      [types.CHANGE_CONTEST_RANK_LIMIT]: () => { s.contest.rankLimit = payload.rankLimit },
      [types.CONTEST_ACCESS]: () => { s.contest.access = payload.access },
      [types.CLEAR_CONTEST]: () => { contestEpoch += 1; s.contest.contest = { created_by: {} }; s.contest.contestProblems = []; s.contest.access = false; s.contest.itemVisible = { menu: true, chart: false, realName: false }; s.contest.forceUpdate = false },
      [types.NOW]: () => { s.contest.now = payload.now },
      [types.NOW_ADD_1S]: () => { s.contest.now = moment(s.contest.now).add(1, 's') }
    }
    if (!handlers[type]) throw new Error(`Unknown mutation ${type}`)
    handlers[type]()
  }
}

export default facade
export { types }
