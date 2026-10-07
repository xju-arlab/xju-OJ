import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { createPinia, defineStore } from 'pinia'
import { shallowRef } from 'vue'
import moment from 'moment'
import * as constants from '../src/utils/constants.js'
import types from '../src/store/types.js'

// Run the actual store with its UI/network dependencies replaced. Pinia and
// Vue stay real so clock and route changes must invalidate cached getters.
const source = fs.readFileSync(new URL('../src/store/index.js', import.meta.url), 'utf8')
  .replace(/^import .*$/gm, '')
  .replaceAll('import.meta.env.DEV', 'false')
  .replace('export const setStoreRouter', 'const setStoreRouter')
  .replace('export default facade', 'globalThis.store = facade')
  .replace('export { types }', 'globalThis.setStoreRouter = setStoreRouter')
const context = vm.createContext({
  ...constants, types, createPinia, defineStore, moment,
  api: {}, runtime: {}, storage: { set () {} },
  i18n: { global: { locale: { value: 'en-US' } } },
  MOCK_CONTESTS: [], MOCK_PROBLEMS: [], cloneFixtures: value => value
})
vm.runInContext(source, context)
const store = context.store
const router = { currentRoute: shallowRef({ params: { contestID: '2' }, meta: {} }) }
context.setStoreRouter(router)
const { CONTEST_STATUS, USER_TYPE } = constants
const contest = {
  id: 2, status: CONTEST_STATUS.ENDED, created_by: { id: 99 },
  start_time: '2026-08-28T13:46:56Z', end_time: '2026-08-29T13:46:56Z',
  contest_type: 'Public', registered: false
}
store.commit(types.CHANGE_CONTEST, { contest })
store.commit(types.NOW, { now: moment('2026-09-11T07:21:00Z') })
assert.equal(store.getters.problemSubmitDisabled, true, 'practice still requires login')
store.commit(types.CHANGE_PROFILE, { profile: { user: { id: 42, admin_type: USER_TYPE.REGULAR_USER } } })
assert.equal(store.getters.contestStatus, CONTEST_STATUS.ENDED)
assert.equal(store.getters.problemSubmitDisabled, false, 'ended public contests allow practice without registration')

store.commit(types.NOW, { now: moment(contest.start_time).subtract(1, 'second') })
assert.equal(store.getters.problemSubmitDisabled, true, 'regular users cannot submit before the start')
store.commit(types.CHANGE_PROFILE, { profile: { user: { id: 99, admin_type: USER_TYPE.ADMIN } } })
assert.equal(store.getters.problemSubmitDisabled, false, 'contest creators can test before the start')
store.commit(types.CHANGE_PROFILE, { profile: { user: { id: 42, admin_type: USER_TYPE.REGULAR_USER } } })
store.commit(types.NOW, { now: moment(contest.end_time).subtract(1, 'second') })
assert.equal(store.getters.problemSubmitDisabled, false)
store.commit(types.NOW_ADD_1S)
store.commit(types.NOW_ADD_1S)
assert.equal(store.getters.contestStatus, CONTEST_STATUS.ENDED)
assert.equal(store.getters.problemSubmitDisabled, false, 'the deadline switches to practice without disabling submissions')

router.currentRoute.value = { params: { contestID: '3' }, meta: {} }
assert.equal(store.getters.problemSubmitDisabled, true, 'wait for the destination contest when changing routes')
router.currentRoute.value = { params: { problemID: '1' }, meta: {} }
assert.equal(store.getters.problemSubmitDisabled, false, 'ordinary practice is independent of the previous contest')
router.currentRoute.value = { params: { contestID: '2' }, meta: {} }
store.commit(types.CLEAR_CONTEST)
assert.equal(store.getters.problemSubmitDisabled, true, 'wait for contest data on a direct problem link')

// Password-protected contests become public practice material after the end.
store.commit(types.CHANGE_CONTEST, { contest: { ...contest, contest_type: 'Password Protected' } })
store.commit(types.CONTEST_ACCESS, { access: false })
store.commit(types.NOW, { now: moment(contest.start_time).subtract(1, 'second') })
assert.equal(store.getters.contestMenuDisabled, true, 'a locked password contest hides its menus before the start')
assert.equal(store.getters.passwordFormVisible, true, 'a locked password contest asks for the password before the start')
store.commit(types.NOW, { now: moment(contest.end_time).add(1, 'second') })
assert.equal(store.getters.contestStatus, CONTEST_STATUS.ENDED)
assert.equal(store.getters.contestMenuDisabled, false, 'an ended password contest opens every menu without the password')
assert.equal(store.getters.passwordFormVisible, false, 'an ended password contest no longer asks for the password')

// A slow previous contest must not replace the destination's permissions,
// problem list, clock or registration state.
const pending = new Map()
context.api.getContest = id => new Promise(resolve => pending.set(id, resolve))
router.currentRoute.value = { params: { contestID: '2' }, meta: {} }
const oldContest = store.dispatch('getContest')
router.currentRoute.value = { params: { contestID: '3' }, meta: {} }
const newContest = store.dispatch('getContest')
pending.get('3')({ data: { data: { ...contest, id: 3, now: '2026-09-11T07:21:00Z' } } })
await newContest
pending.get('2')({ data: { data: { ...contest, id: 2, now: '2026-08-28T13:00:00Z' } } })
await oldContest
assert.equal(store.state.contest.contest.id, 3)
assert.equal(store.getters.contestStatus, CONTEST_STATUS.ENDED)

let resolveProblems, resolveAccess, resolveRegistration
context.api.getContestProblemList = () => new Promise(resolve => { resolveProblems = resolve })
context.api.getContestAccess = () => new Promise(resolve => { resolveAccess = resolve })
context.api.registerContest = () => new Promise(resolve => { resolveRegistration = resolve })
const oldProblems = store.dispatch('getContestProblems')
const oldAccess = store.dispatch('getContestAccess')
const oldRegistration = store.dispatch('registerContest')
store.commit(types.CLEAR_CONTEST)
resolveProblems({ data: { data: [{ _id: 'stale' }] } })
resolveAccess({ data: { data: { access: true } } })
resolveRegistration({ data: { data: {} } })
await Promise.all([oldProblems, oldAccess, oldRegistration])
assert.equal(store.state.contest.contestProblems.length, 0)
assert.equal(store.state.contest.access, false)
assert.notEqual(store.state.contest.contest.registered, true)

console.log('contest submission permissions and stale response isolation passed')
