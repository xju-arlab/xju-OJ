'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const OJ_ORIGIN = 'https://oj.icthub.top'
const source = fs.readFileSync(
  path.resolve(__dirname, '../static/userscripts/xju-oj-remote-bridge.user.js'),
  'utf8'
)

class FakeFormData {
  constructor () {
    this.values = new Map()
  }

  set (name, value) { this.values.set(name, value) }
  append (name, value) { this.values.set(name, value) }
  delete (name) { this.values.delete(name) }
}

class FakeFile {
  constructor (parts, name, options) {
    this.parts = parts
    this.name = name
    this.options = options
  }
}

function emptyDocument () {
  return {
    title: '',
    forms: [],
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: () => null
  }
}

function codeforcesProblemDocument () {
  const language = { name: 'programTypeId', options: [{ value: '54' }] }
  const sourceFile = { name: 'sourceFile' }
  const submitter = { name: 'action', value: 'submit' }
  const form = {
    getAttribute: name => name === 'action' ? '/problemset/submit' : '',
    querySelector: selector => {
      if (selector === '[name="programTypeId"]') return language
      if (selector === '[name="sourceFile"], [name="source"]') return sourceFile
      if (selector === 'input[type="file"][name="sourceFile"]') return sourceFile
      if (selector === 'button[type="submit"][name], input[type="submit"][name]') return submitter
      return null
    }
  }
  return {
    ...emptyDocument(),
    title: 'Watermelon - Codeforces',
    forms: [form],
    querySelectorAll: selector => selector === '#header a[href^="/profile/"]'
      ? [{ getAttribute: () => '/profile/tester' }]
      : []
  }
}

function luoguProblemDocument () {
  return {
    ...emptyDocument(),
    title: 'P1001 A+B Problem',
    getElementById: id => id === 'lentille-context'
      ? { textContent: JSON.stringify({ user: { uid: 1 } }) }
      : null,
    querySelector: selector => selector === 'meta[name="csrf-token"]'
      ? { getAttribute: () => 'csrf-token' }
      : null
  }
}

function makeDomParser () {
  return class FakeDOMParser {
    parseFromString (html) {
      if (html === 'CF_PROBLEM') return codeforcesProblemDocument()
      if (html === 'CF_CHALLENGE') return {
        ...emptyDocument(),
        title: 'Just a moment...'
      }
      if (html === 'LUOGU_PROBLEM') return luoguProblemDocument()
      return emptyDocument()
    }
  }
}

function jsonResponse (payload, extra = {}) {
  return {
    status: 200,
    responseText: JSON.stringify(payload),
    finalUrl: '',
    ...extra
  }
}

function taskFor (provider) {
  const common = {
    schema: 'xju-oj.remote-submit.v1',
    submission_id: `submission-${provider.toLowerCase()}`,
    user_id: 1,
    rule_type: 'ACM',
    provider,
    language: 'C++',
    created_at: new Date().toISOString()
  }
  if (provider === 'CODEFORCES') {
    return {
      ...common,
      problem_id: '4A',
      language_id: '54',
      target_url: 'https://codeforces.com/problemset/problem/4/A',
      provider_data: { contest_id: 4, index: 'A' }
    }
  }
  if (provider === 'LUOGU') {
    return {
      ...common,
      problem_id: 'P1001',
      language_id: '28',
      target_url: 'https://www.luogu.com.cn/problem/P1001',
      provider_data: { problem_id: 'P1001' }
    }
  }
  return {
    ...common,
    problem_id: 'NC322024',
    language_id: '3',
    target_url: 'https://ac.nowcoder.com/acm/problem/322024',
    provider_data: { problem_id: 'NC322024', question_id: '11742270', tag_id: 0 }
  }
}

async function waitFor (predicate) {
  for (let attempt = 0; attempt < 50; ++attempt) {
    if (predicate()) return
    await new Promise(resolve => setImmediate(resolve))
  }
  assert.fail('userscript scenario did not finish')
}

async function runScenario (provider, mode = 'success', records = []) {
  const listeners = new Map()
  const valueListeners = new Map()
  const storage = new Map()
  const backendEvents = []
  const openedTabs = []
  let codeforcesApiCalls = 0
  let luoguRecordRequestHeaders = null
  let luoguRecordRequests = 0
  let activeBackendRequests = 0
  let maxActiveBackendRequests = 0

  const documentElement = {
    attributes: new Map(),
    setAttribute (name, value) { this.attributes.set(name, String(value)) },
    getAttribute (name) { return this.attributes.get(name) || '' }
  }
  const document = {
    ...emptyDocument(),
    documentElement,
    readyState: 'complete',
    cookie: ''
  }
  const window = {
    location: {
      origin: OJ_ORIGIN,
      hostname: 'oj.icthub.top',
      pathname: '/contest/2/problem/A',
      hash: ''
    },
    addEventListener (name, handler) {
      const handlers = listeners.get(name) || []
      handlers.push(handler)
      listeners.set(name, handlers)
    },
    dispatchEvent (event) {
      for (const handler of listeners.get(event.type) || []) handler(event)
      return true
    },
    setTimeout (handler, delay) {
      if (delay < 5000) queueMicrotask(handler)
      return 1
    },
    clearTimeout () {},
    fetch (_url, options) {
      if (options && options.body) backendEvents.push(JSON.parse(options.body))
      activeBackendRequests += 1
      maxActiveBackendRequests = Math.max(maxActiveBackendRequests, activeBackendRequests)
      return new Promise(resolve => queueMicrotask(() => {
        activeBackendRequests -= 1
        const event = options && options.body ? JSON.parse(options.body) : null
        resolve({ ok: true, json: async () => ({ error: null, data: event ? { id: event.submission_id, remote_status: event.status } : { user_id: 1, tasks: [] } }) })
      }))
    },
    focus () {}
  }
  window.window = window

  function remoteResponse (request) {
    const url = request.url
    if (provider === 'NOWCODER') {
      if (url.includes('/profile/user-info-v2')) {
        return mode === 'auth'
          ? jsonResponse({ msg: '请先登录' }, { status: 401 })
          : jsonResponse({ code: 0, data: { userId: 123, isMember: false } })
      }
      if (url.includes('/access-token')) {
        return jsonResponse({ success: true, data: { accessToken: 'token' } })
      }
      if (url.endsWith('/api/service/judge/submit')) {
        return mode === 'verification'
          ? jsonResponse({ code: 1, msg: '请完成安全验证' })
          : jsonResponse({ code: 0, data: { id: 456 } })
      }
      if (url.includes('/submit-status')) {
        return jsonResponse({
          code: 0,
          data: {
            status: 3,
            judgeReplyDesc: 'ACCEPTED',
            timeConsumption: 1,
            memoryConsumption: 1,
            rightCaseNum: 1,
            allCaseNum: 1
          }
        })
      }
    }
    if (provider === 'LUOGU') {
      if (request.method === 'GET' && url.includes('/problem/P1001')) {
        return { status: 200, responseText: 'LUOGU_PROBLEM', finalUrl: url }
      }
      if (request.method === 'POST' && url.includes('/fe/api/problem/submit/P1001')) {
        if (mode === 'captcha-id') {
          return jsonResponse({
            errorType: 'Luogu\\Exception\\CaptchaNotMatchException',
            errorData: { interactive: { type: 'TNSTL', state: 'captcha-state' } },
            data: { id: 'captcha-challenge-id' },
            message: '请完成人机验证'
          }, { status: 403 })
        }
        return jsonResponse({ rid: 789 })
      }
      if (url.includes('/record/789')) {
        luoguRecordRequestHeaders = request.headers || {}
        luoguRecordRequests += 1
        if (records.length) {
          return jsonResponse({
            data: { record: records[Math.min(luoguRecordRequests - 1, records.length - 1)] }
          })
        }
        if (mode === 'auth') {
          return jsonResponse({ instance: 'auth', template: 'login', status: 200, data: {}, user: null })
        }
        if (mode === 'verification') {
          return { status: 200, responseText: '<html>browser verification</html>', finalUrl: url }
        }
        const compileFailed = mode === 'compile-error'
        if (mode === 'direct-record') {
          return jsonResponse({
            code: 200,
            currentTemplate: 'RecordShow',
            currentData: {
              id: 789,
              status: 12,
              time: 1,
              memory: 1,
              score: 100,
              detail: { judgeResult: { finishedCaseCount: 2 } }
            },
            currentUser: { uid: 1 }
          })
        }
        return jsonResponse({
          code: 200,
          currentTemplate: 'RecordShow',
          currentData: {
            record: {
              id: 789,
              status: compileFailed ? 2 : 12,
              time: 1,
              memory: 1,
              score: compileFailed ? 0 : 100,
              detail: compileFailed ? {
                compileResult: { message: 'compile failed' }
              } : {
                judgeResult: {
                  finishedCaseCount: 2,
                  subtasks: [{
                    testCases: [
                      { id: 1, status: 12 },
                      { id: 2, status: 12 }
                    ]
                  }]
                }
              }
            }
          },
          currentUser: { uid: 1 }
        })
      }
    }
    if (provider === 'CODEFORCES') {
      if (request.method === 'GET' && url.includes('/problemset/problem/4/A')) {
        if (mode === 'connection') throw new Error('network unavailable')
        return mode === 'verification'
          ? { status: 403, responseText: 'CF_CHALLENGE', finalUrl: url }
          : { status: 200, responseText: 'CF_PROBLEM', finalUrl: url }
      }
      if (url.includes('/api/user.status')) {
        codeforcesApiCalls += 1
        return jsonResponse({
          status: 'OK',
          result: codeforcesApiCalls === 1 ? [] : [{
            id: 999,
            contestId: 4,
            creationTimeSeconds: Math.floor(Date.now() / 1000),
            problem: { contestId: 4, index: 'A' },
            verdict: 'OK',
            timeConsumedMillis: 1,
            memoryConsumedBytes: 1024,
            passedTestCount: 1
          }]
        })
      }
      if (request.method === 'POST' && url.includes('/problemset/submit')) {
        if (mode === 'post-connection') throw new Error('connection lost after submit')
        return { status: 200, responseText: 'CF_SUBMIT', finalUrl: 'https://codeforces.com/submissions/tester' }
      }
    }
    throw new Error(`unexpected request: ${request.method} ${url}`)
  }

  const context = vm.createContext({
    console,
    window,
    document,
    unsafeWindow: window,
    URL,
    TextEncoder,
    AbortController,
    FormData: FakeFormData,
    File: FakeFile,
    DOMParser: makeDomParser(),
    CustomEvent: class CustomEvent {
      constructor (type, options = {}) {
        this.type = type
        this.detail = options.detail
      }
    },
    MutationObserver: class MutationObserver {
      observe () {}
      disconnect () {}
    },
    GM_info: { script: { version: '1.1.0' } },
    GM_getValue: (key, fallback) => storage.has(key) ? storage.get(key) : fallback,
    GM_setValue: (key, value) => {
      const previous = storage.get(key)
      storage.set(key, value)
      for (const listener of valueListeners.get(key) || []) listener(key, previous, value, false)
    },
    GM_deleteValue: key => storage.delete(key),
    GM_listValues: () => [...storage.keys()],
    GM_addValueChangeListener: (key, listener) => {
      const handlers = valueListeners.get(key) || []
      handlers.push(listener)
      valueListeners.set(key, handlers)
      return handlers.length
    },
    GM_openInTab: (url, options = {}) => openedTabs.push({ url, options }),
    GM_registerMenuCommand: () => {},
    GM_xmlhttpRequest: request => queueMicrotask(() => {
      try {
        request.onload(remoteResponse(request))
      } catch (error) {
        request.onerror(error)
      }
    }),
    setTimeout: window.setTimeout,
    clearTimeout: window.clearTimeout,
    queueMicrotask
  })

  vm.runInContext(source, context, { filename: 'xju-oj-remote-bridge.user.js' })
  const submitHandler = (listeners.get('xju-oj:remote-bridge:submit') || [])[0]
  assert.ok(submitHandler, 'submit listener was not installed')
  await submitHandler({ detail: { task: taskFor(provider), code: 'int main() { return 0; }' } })

  const terminalStatus = mode === 'success' || mode === 'compile-error' || mode === 'direct-record'
    ? 'FINISHED'
    : mode === 'auth'
      ? 'AUTH_REQUIRED'
      : mode === 'connection' || mode === 'post-connection' ? 'OPENING' : 'VERIFICATION_REQUIRED'
  await waitFor(() => backendEvents.some(event => event.status === terminalStatus))
  return { backendEvents, openedTabs, maxActiveBackendRequests, luoguRecordRequestHeaders, luoguRecordRequests }
}

;(async () => {
  for (const provider of ['CODEFORCES', 'LUOGU', 'NOWCODER']) {
    const result = await runScenario(provider)
    assert.equal(result.openedTabs.length, 0, `${provider} opened a tab for a normal submission`)
    assert.ok(result.backendEvents.some(event => event.status === 'FINISHED'))
    if (provider === 'LUOGU') {
      assert.ok(result.luoguRecordRequestHeaders)
      assert.equal(
        Object.keys(result.luoguRecordRequestHeaders)
          .some(header => header.toLowerCase() === 'content-type'),
        false,
        'Luogu record GET must not send Content-Type; Luogu rejects it with HTTP 403'
      )
    }
    assert.equal(result.maxActiveBackendRequests, 1, `${provider} posted backend events concurrently`)
    assert.equal(result.backendEvents.at(-1).status, 'FINISHED', `${provider} did not deliver its final event`)
  }

  const auth = await runScenario('NOWCODER', 'auth')
  assert.equal(auth.openedTabs.length, 1)
  assert.ok(auth.backendEvents.some(event => event.status === 'AUTH_REQUIRED'))

  const verification = await runScenario('NOWCODER', 'verification')
  assert.equal(verification.openedTabs.length, 1)
  assert.ok(verification.backendEvents.some(event => event.status === 'VERIFICATION_REQUIRED'))

  const luoguAuth = await runScenario('LUOGU', 'auth')
  assert.equal(luoguAuth.openedTabs.length, 1)
  assert.ok(luoguAuth.backendEvents.some(event => event.status === 'AUTH_REQUIRED'))

  const luoguVerification = await runScenario('LUOGU', 'verification')
  assert.equal(luoguVerification.openedTabs.length, 1)
  assert.ok(luoguVerification.backendEvents.some(event => event.status === 'VERIFICATION_REQUIRED'))

  const luoguCompileError = await runScenario('LUOGU', 'compile-error')
  assert.equal(luoguCompileError.openedTabs.length, 0)
  assert.equal(
    luoguCompileError.backendEvents.find(event => event.status === 'FINISHED').verdict,
    'COMPILE_ERROR'
  )

  const acceptedRecord = { id: 789, status: 12, score: 100, time: 5, memory: 432 }
  for (const success of [true, undefined]) {
    const compileResult = { success, message: 'Compilation completed with warnings' }
    const compiling = await runScenario('LUOGU', 'success', [
      { id: 789, status: 1, score: 0, detail: { compileResult } },
      { ...acceptedRecord, detail: { compileResult } }
    ])
    assert.equal(compiling.luoguRecordRequests, 2, 'compiler output must not finish a pending record')
    const finished = compiling.backendEvents.find(event => event.status === 'FINISHED')
    assert.equal(finished.verdict, 'ACCEPTED')
    assert.equal(finished.score, 100)
    assert.equal(finished.time_ms, 5)
    assert.equal(finished.memory_bytes, 432 * 1024)
  }

  for (const [status, verdict] of [[2, 'COMPILE_ERROR'], [4, 'MEMORY_LIMIT_EXCEEDED'], [5, 'TIME_LIMIT_EXCEEDED'], [6, 'WRONG_ANSWER'], [12, 'ACCEPTED'], [14, 'WRONG_ANSWER']]) {
    const result = await runScenario('LUOGU', 'success', [{
      id: 789,
      status,
      detail: { judgeResult: { subtasks: [{ testCases: [{ status: 12 }] }] } }
    }])
    assert.equal(result.backendEvents.find(event => event.status === 'FINISHED').verdict, verdict,
      'the overall verdict must take precedence over incomplete testcase details')
  }

  const pendingCases = await runScenario('LUOGU', 'success', [
    { id: 789, status: 1, detail: { judgeResult: { subtasks: [{ testCases: [{ status: 12 }] }] } } },
    acceptedRecord
  ])
  assert.equal(pendingCases.luoguRecordRequests, 2, 'passed cases must not finish a judging record')

  const genuineCompileError = await runScenario('LUOGU', 'success', [{
    id: 789,
    status: 2,
    detail: { compileResult: { success: false, message: 'main.cpp: error: expected semicolon' } }
  }])
  const compileEvent = genuineCompileError.backendEvents.find(event => event.status === 'FINISHED')
  assert.equal(compileEvent.verdict, 'COMPILE_ERROR')
  assert.match(compileEvent.message, /expected semicolon/)

  const luoguDirectRecord = await runScenario('LUOGU', 'direct-record')
  assert.equal(luoguDirectRecord.openedTabs.length, 0)
  assert.equal(
    luoguDirectRecord.backendEvents.find(event => event.status === 'FINISHED').verdict,
    'ACCEPTED'
  )

  const luoguCaptchaId = await runScenario('LUOGU', 'captcha-id')
  assert.equal(luoguCaptchaId.openedTabs.length, 1)
  assert.ok(luoguCaptchaId.backendEvents.some(event => event.status === 'VERIFICATION_REQUIRED'))
  assert.equal(luoguCaptchaId.backendEvents.some(event => event.status === 'SUBMITTED'), false)

  const codeforcesVerification = await runScenario('CODEFORCES', 'verification')
  assert.equal(codeforcesVerification.openedTabs.length, 1)
  assert.equal(codeforcesVerification.openedTabs[0].options.active, false)
  assert.ok(codeforcesVerification.backendEvents.some(event => event.status === 'VERIFICATION_REQUIRED'))

  const codeforcesConnection = await runScenario('CODEFORCES', 'connection')
  assert.equal(codeforcesConnection.openedTabs.length, 1)
  assert.equal(codeforcesConnection.openedTabs[0].options.active, true)
  assert.equal(codeforcesConnection.backendEvents.some(event => event.status === 'FAILED'), false)

  const codeforcesPostConnection = await runScenario('CODEFORCES', 'post-connection')
  assert.equal(codeforcesPostConnection.openedTabs.length, 1)
  assert.equal(codeforcesPostConnection.backendEvents.some(event => event.status === 'FAILED'), false)

  console.log('remote bridge runtime passed')
})().catch(error => {
  console.error(error)
  process.exitCode = 1
})
