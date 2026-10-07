'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(path.resolve(__dirname, '../static/userscripts/xju-oj-remote-bridge.user.js'), 'utf8')
const cut = source.indexOf('\n  window.addEventListener(PING_EVENT, announce)')
assert.ok(cut > 0)
const instrumented = source.slice(0, cut) + `
  globalThis.bridge = { sanitizeBridgePayload, saveTask, publishBridgeEvent, bootOjBridge,
    resumeOjJudgingTask, startRemoteTask, luoguStatusDetails, findCodeforcesRun, nativeSubmissionTask, sendProviderCode,
    setUser(id) { currentOjUserId = id }, outboxKey, taskStorageKey };
})()`
const prefix = 'xju-oj:remote-bridge:v1'
const task = (id = 'synthetic', provider = 'NOWCODER') => ({
  schema: 'xju-oj.remote-submit.v1', user_id: 1, submission_id: id, provider,
  rule_type: 'ACM', language: 'C++', language_id: '3', problem_id: 'NC15189',
  status: 'JUDGING', remote_submission_id: `run-${id}`,
  target_url: 'https://ac.nowcoder.com/acm/problem/15189',
  adapter_state: { phase: 'JUDGING', submission_id: `run-${id}`, token: 'synthetic', user_id: 12, app_id: 5 }
})
const settle = async () => { for (let i = 0; i < 40; ++i) await Promise.resolve() }

function sharedState () {
  const shared = { now: 1000000, storage: new Map(), timers: new Map(), listeners: new Map(), serial: 0 }
  shared.advance = async milliseconds => {
    const until = shared.now + milliseconds
    await settle()
    for (let guard = 0; guard < 10000; ++guard) {
      const next = [...shared.timers.entries()].sort((a, b) => a[1].at - b[1].at)[0]
      if (!next || next[1].at > until) break
      shared.now = next[1].at
      shared.timers.delete(next[0])
      next[1].handler()
      await settle()
      assert.ok(guard < 9999, 'unexpected busy retry loop')
    }
    shared.now = until
    await settle()
  }
  return shared
}

function browser (shared = sharedState(), options = {}) {
  const backendEvents = [], providerRequests = [], requests = [], notices = []
  let failures = options.failures || []
  const window = {
    location: { origin: 'https://oj.icthub.top', hostname: 'oj.icthub.top', hash: '', pathname: '/' },
    addEventListener () {}, focus () {},
    dispatchEvent (event) { notices.push(event.detail) },
    setTimeout (handler, delay) {
      const id = ++shared.serial
      shared.timers.set(id, { at: shared.now + delay, handler })
      return id
    },
    clearTimeout: id => shared.timers.delete(id),
    async fetch (url, init = {}) {
      requests.push(url)
      if (!init.body) return { ok: true, json: async () => ({ error: null, data: { user_id: options.userId || 1, tasks: options.recovery || [] } }) }
      const event = JSON.parse(init.body)
      backendEvents.push(event)
      const failure = failures.shift()
      if (failure === 'network') throw new Error('offline')
      if (failure === 'http') return { ok: false, status: 503 }
      if (failure === 'application') return { ok: true, json: async () => ({ error: 'invalid-score', data: 'bad optional metric' }) }
      if (failure === 'unconfirmed') return { ok: true, json: async () => ({ error: null, data: { id: event.submission_id, remote_status: 'JUDGING' } }) }
      if (failure === 'hang') return new Promise((resolve, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted'))))
      return { ok: true, json: async () => ({ error: null, data: { id: event.submission_id, remote_status: event.status } }) }
    }
  }
  const context = vm.createContext({
    window, unsafeWindow: window, document: { cookie: '' }, URL, TextEncoder, AbortController,
    Date: class extends Date { static now () { return shared.now } },
    CustomEvent: class { constructor (type, options) { this.type = type; this.detail = options.detail } },
    GM_getValue: (key, fallback) => structuredClone(shared.storage.has(key) ? shared.storage.get(key) : fallback),
    GM_setValue: (key, value) => {
      const previous = shared.storage.get(key)
      shared.storage.set(key, structuredClone(value))
      for (const listener of shared.listeners.get(key) || []) queueMicrotask(() => listener(key, previous, structuredClone(value)))
    },
    GM_deleteValue: key => shared.storage.delete(key),
    GM_listValues: () => [...shared.storage.keys()],
    GM_addValueChangeListener: (key, listener) => {
      if (!shared.listeners.has(key)) shared.listeners.set(key, [])
      shared.listeners.get(key).push(listener)
    },
    GM_xmlhttpRequest (request) {
      providerRequests.push(request)
      let payload
      if (request.url.includes('/profile/user-info')) payload = { code: 0, data: { userId: 12 } }
      else if (request.url.includes('/access-token')) payload = { success: true, data: { accessToken: 'synthetic-refresh' } }
      else payload = options.providerResponse ? options.providerResponse(shared.now, request) : {
        code: 0, data: { status: 3, judgeReplyDesc: '编译错误', rightHundredRate: 'NaN', memo: 'compiler error', timeConsumption: 0, memoryConsumption: 0 }
      }
      queueMicrotask(() => request.onload({ status: 200, responseText: JSON.stringify(payload) }))
    }
  })
  vm.runInContext(instrumented, context)
  context.bridge.setUser(options.userId || 1)
  return { bridge: context.bridge, window, shared, backendEvents, providerRequests, requests, notices }
}

;(async () => {
  const clean = browser().bridge.sanitizeBridgePayload({ score: NaN, time_ms: Infinity, memory_bytes: -1, passed_tests: 1.5, total_tests: true, message: 'x\0'.repeat(3000) })
  assert.deepEqual(JSON.parse(JSON.stringify(clean)), { message: 'x'.repeat(2048) })
  assert.equal(browser().bridge.sanitizeBridgePayload({ score: '75.5%' }).score, 75.5)

  for (const failure of ['http', 'application', 'network', 'unconfirmed', 'hang']) {
    const env = browser(undefined, { failures: [failure] })
    const submission = task(failure)
    env.bridge.saveTask(submission)
    env.bridge.publishBridgeEvent(submission, 'FINISHED', { remote_submission_id: submission.remote_submission_id, verdict: 'ACCEPTED' })
    await env.shared.advance(failure === 'hang' ? 20100 : 100)
    assert.ok(env.shared.storage.has(env.bridge.taskStorageKey(submission.submission_id)), `${failure}: removed task before acknowledgement`)
    assert.ok(env.shared.storage.has(env.bridge.outboxKey(submission.submission_id)))
    await env.shared.advance(3000)
    assert.equal(env.backendEvents.length, 2, `${failure}: final event was not retried`)
    assert.equal(env.shared.storage.has(env.bridge.taskStorageKey(submission.submission_id)), false)
    assert.equal(env.shared.storage.has(env.bridge.outboxKey(submission.submission_id)), false)
  }

  const old = browser(undefined, { failures: ['network'] })
  old.bridge.saveTask(task('reload'))
  old.bridge.publishBridgeEvent(task('reload'), 'FINISHED', { remote_submission_id: 'run-reload', verdict: 'ACCEPTED' })
  await old.shared.advance(100)
  old.shared.timers.clear() // Simulate closing the originating tab.
  const reloaded = browser(old.shared)
  reloaded.bridge.bootOjBridge()
  await old.shared.advance(300)
  assert.equal(reloaded.backendEvents.at(-1).status, 'FINISHED')
  assert.equal(old.shared.storage.has(`${prefix}:task:reload`), false)

  const deferred = browser(undefined, { providerResponse: now => ({
    code: 0, data: now < 1121000 ? { status: 2 } : { status: 3, judgeReplyDesc: 'ACCEPTED' }
  }) })
  deferred.bridge.saveTask(task('slow'))
  const slow = deferred.bridge.resumeOjJudgingTask(task('slow'))
  await deferred.shared.advance(121000)
  await slow
  assert.ok(deferred.backendEvents.some(event => event.status === 'JUDGING'))
  await deferred.shared.advance(6000)
  assert.ok(deferred.backendEvents.some(event => event.status === 'FINISHED'), 'polling was not resumed beyond two minutes')

  const multi = sharedState()
  const first = browser(multi), second = browser(multi)
  first.bridge.saveTask(task('shared'))
  first.bridge.resumeOjJudgingTask(task('shared'))
  second.bridge.resumeOjJudgingTask(task('shared'))
  await multi.advance(300)
  assert.equal(first.providerRequests.length + second.providerRequests.length, 1, 'both tabs queried the same run')

  const wrongUser = browser(undefined, { userId: 2 })
  wrongUser.bridge.saveTask(task('private'))
  wrongUser.bridge.publishBridgeEvent(task('private'), 'FINISHED', { verdict: 'ACCEPTED' })
  wrongUser.bridge.resumeOjJudgingTask(task('private'))
  await wrongUser.shared.advance(300)
  assert.equal(wrongUser.backendEvents.length, 0)
  assert.equal(wrongUser.providerRequests.length, 0)

  const recovery = browser(undefined, { recovery: [{ ...task('historical'), adapter_state: undefined }] })
  recovery.bridge.bootOjBridge()
  await recovery.shared.advance(500)
  assert.ok(recovery.backendEvents.some(event => event.status === 'FINISHED'))
  assert.ok(recovery.providerRequests.every(request => request.method === 'GET'), 'recovery must not submit code again')
  assert.equal(recovery.backendEvents.at(-1).score, undefined, 'NaN score should be omitted')

  const exact = browser().bridge.findCodeforcesRun([{ id: 2 }, { id: 3 }], { remote_submission_id: '2' })
  assert.equal(exact.id, 2, 'recovery must use the original remote ID')

  const native = browser()
  const nativeTask = { ...task('native'), remote_submission_id: null, code: 'synthetic code', provider_data: { question_id: '42' } }
  native.window.__xjuOjRemoteBridgeNowcoderTask = nativeTask
  assert.equal(native.bridge.nativeSubmissionTask('NOWCODER', '/api/service/judge/submit', { questionId: '43' }), null)
  assert.equal(native.bridge.nativeSubmissionTask('NOWCODER', '/api/service/judge/submit', { questionId: '42' }).submission_id, 'native')
  native.window.__xjuOjRemoteBridgeLuoguTask = { ...nativeTask, problem_id: 'P1001', provider_data: { problem_id: 'P1001' } }
  assert.equal(native.bridge.nativeSubmissionTask('LUOGU', '/fe/api/problem/submit/P1002'), null)
  assert.equal(native.bridge.nativeSubmissionTask('LUOGU', '/fe/api/problem/submit/P1001').submission_id, 'native')
  native.window.__xjuOjRemoteBridgeLuoguTask.remote_submission_id = '123'
  assert.equal(native.bridge.nativeSubmissionTask('LUOGU', '/fe/api/problem/submit/P1001'), null)

  const uncertain = browser()
  const pending = { ...nativeTask, adapter_state: {} }
  uncertain.bridge.saveTask(pending)
  let sends = 0
  const send = () => { sends++; const error = new Error('connection lost'); error.remoteConnection = true; throw error }
  const interrupted = uncertain.bridge.sendProviderCode(pending, send).catch(error => error)
  await uncertain.shared.advance(100)
  assert.equal((await interrupted).submitUncertain, true)
  const retry = uncertain.bridge.sendProviderCode(pending, send).catch(error => error)
  await uncertain.shared.advance(100)
  assert.equal((await retry).submitUncertain, true)
  assert.equal(sends, 1, 'an uncertain POST must never be automatically repeated')
  assert.equal(uncertain.shared.storage.get(`${prefix}:task:native`).adapter_state.phase, 'SUBMIT_UNCERTAIN')
  console.log('remote bridge reliability passed: acknowledgement, retries, timeout, refresh, leases, ownership, historical recovery and invalid metrics')
})().catch(error => { console.error(error); process.exitCode = 1 })
