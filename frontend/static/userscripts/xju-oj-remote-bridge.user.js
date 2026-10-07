// ==UserScript==
// @name         XJU-OJ 远程提交助手
// @name:zh-CN   XJU-OJ 远程提交助手
// @name:en      XJU-OJ Remote Submission Bridge
// @namespace    https://oj.icthub.top/
// @version      1.1.0
// @description  在用户自己的洛谷、牛客和 Codeforces 登录会话中转发 XJU-OJ 练习提交。
// @description:en Forward XJU-OJ practice submissions through the user's own Luogu, Nowcoder, and Codeforces sessions.
// @author       XJU-OJ
// @homepageURL  https://oj.icthub.top/remote-bridge
// @supportURL   https://oj.icthub.top/remote-bridge
// @downloadURL  https://oj.icthub.top/static/userscripts/xju-oj-remote-bridge.user.js
// @updateURL    https://oj.icthub.top/static/userscripts/xju-oj-remote-bridge.user.js
// @icon         https://oj.icthub.top/public/website/favicon.ico
// @match        https://oj.icthub.top/*
// @match        https://www.luogu.com.cn/*
// @match        https://ac.nowcoder.com/*
// @match        https://www.nowcoder.com/*
// @match        https://codeforces.com/*
// @match        https://www.codeforces.com/*
// @run-at       document-start
// @grant        GM_info
// @grant        GM_openInTab
// @grant        GM_registerMenuCommand
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_deleteValue
// @grant        GM_listValues
// @grant        GM_addValueChangeListener
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      www.nowcoder.com
// @connect      gw-c.nowcoder.com
// @connect      victorinox.nowcoder.com
// @connect      codeforces.com
// @connect      www.codeforces.com
// @connect      luogu.com.cn
// @connect      www.luogu.com.cn
// ==/UserScript==

(function () {
  'use strict'

  const OJ_ORIGIN = 'https://oj.icthub.top'
  const TASK_SCHEMA = 'xju-oj.remote-submit.v1'
  const IMPORT_SCHEMA = 'xju-oj.remote-import.v1'
  const STORAGE_PREFIX = 'xju-oj:remote-bridge:v1'
  const READY_ATTRIBUTE = 'data-xju-oj-remote-bridge-version'
  const PROVIDER_ATTRIBUTE = 'data-xju-oj-remote-bridge-provider'
  const READY_EVENT = 'xju-oj:remote-bridge:ready'
  const PING_EVENT = 'xju-oj:remote-bridge:ping'
  const SUBMIT_EVENT = 'xju-oj:remote-bridge:submit'
  const BRIDGE_EVENT = 'xju-oj:remote-bridge:event'
  const IMPORT_EVENT = 'xju-oj:remote-bridge:import'
  const IMPORT_RESULT_EVENT = 'xju-oj:remote-bridge:import-event'
  const EVENT_STORAGE_KEY = `${STORAGE_PREFIX}:event`
  const IMPORT_EVENT_STORAGE_KEY = `${STORAGE_PREFIX}:import-event`
  const MAX_CODE_SIZE = 1024 * 1024
  const BACKEND_EVENT_FIELDS = [
    'submission_id', 'provider', 'status', 'remote_submission_id', 'remote_url',
    'verdict', 'message', 'time_ms', 'memory_bytes', 'passed_tests', 'total_tests',
    'score', 'verification_source', 'failed_verdict'
  ]
  const dispatchedBridgeEvents = new Set()
  const ojPollingSubmissions = new Set()
  const backendEventQueues = new Map()
  const deliveryTimers = new Map()
  const pollTimers = new Map()
  const activePollLeases = new Map()
  const startingSubmissions = new Set()
  const deliveryAttempts = new Map()
  const tabId = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  const TERMINAL_STATUSES = new Set(['FINISHED', 'FAILED'])
  const ACTION_STATUSES = new Set(['AUTH_REQUIRED', 'VERIFICATION_REQUIRED'])
  const ownedSubmissionIds = new Set()
  let currentOjUserId = null
  let recovering = false
  let recoveryTimer = null
  const PROVIDER_HOSTS = {
    LUOGU: new Set(['www.luogu.com.cn', 'luogu.com.cn']),
    NOWCODER: new Set(['ac.nowcoder.com', 'www.nowcoder.com', 'nowcoder.com']),
    CODEFORCES: new Set(['codeforces.com', 'www.codeforces.com'])
  }
  const version = (typeof GM_info !== 'undefined' && GM_info.script && GM_info.script.version) || 'unknown'

  function currentProvider () {
    const host = window.location.hostname
    if (PROVIDER_HOSTS.LUOGU.has(host)) return 'LUOGU'
    if (PROVIDER_HOSTS.NOWCODER.has(host)) return 'NOWCODER'
    if (PROVIDER_HOSTS.CODEFORCES.has(host)) return 'CODEFORCES'
    if (window.location.origin === OJ_ORIGIN) return 'XJU_OJ'
    return null
  }

  function taskStorageKey (submissionId) {
    return `${STORAGE_PREFIX}:task:${submissionId}`
  }

  function activeTaskStorageKey (provider) {
    return `${STORAGE_PREFIX}:active:${provider}`
  }

  function importTaskStorageKey (requestId) {
    return `${STORAGE_PREFIX}:import:${requestId}`
  }

  function activeImportStorageKey (provider) {
    return `${STORAGE_PREFIX}:active-import:${provider}`
  }

  function cookieValue (name) {
    const prefix = `${encodeURIComponent(name)}=`
    const item = document.cookie.split(';').map(value => value.trim()).find(value => value.startsWith(prefix))
    return item ? decodeURIComponent(item.slice(prefix.length)) : ''
  }

  function outboxKey (id) {
    return `${STORAGE_PREFIX}:outbox:${id}`
  }

  function sanitizeBridgePayload (event) {
    const payload = {}
    for (const field of BACKEND_EVENT_FIELDS) {
      if (event[field] !== undefined && event[field] !== null) payload[field] = event[field]
    }
    for (const field of ['score', 'time_ms', 'memory_bytes', 'passed_tests', 'total_tests']) {
      if (payload[field] === undefined) continue
      const raw = payload[field]
      const value = typeof raw === 'boolean' || String(raw).trim() === ''
        ? NaN : Number(String(raw).trim().replace(/%$/, ''))
      if (!Number.isFinite(value) || value < 0 || value > Number.MAX_SAFE_INTEGER ||
          (field !== 'score' && !Number.isSafeInteger(value))) delete payload[field]
      else payload[field] = value
    }
    if (payload.message !== undefined) payload.message = String(payload.message).replace(/\0/g, '').slice(0, 2048)
    return payload
  }

  async function ojRequest (url, options = {}) {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), 20000)
    try {
      const response = await window.fetch(url, { credentials: 'same-origin', ...options, signal: controller.signal })
      if (!response.ok) throw new Error(`OJ HTTP ${response.status}`)
      const payload = await response.json()
      if (!payload || payload.error !== null) throw new Error(String((payload && payload.data) || 'OJ 未确认请求'))
      return payload.data
    } finally {
      window.clearTimeout(timer)
    }
  }

  // GM storage spans the OJ and provider origins. Leases prevent every open tab
  // from polling the same run; an abandoned tab's lease expires automatically.
  async function acquireLease (id, lane) {
    const key = `${STORAGE_PREFIX}:lease:${lane}:${id}`
    const previous = GM_getValue(key, null)
    if (previous && previous.owner !== tabId && previous.expires > Date.now()) return null
    GM_setValue(key, { owner: tabId, expires: Date.now() + 45000 })
    await sleep(50)
    if ((GM_getValue(key, {}) || {}).owner !== tabId) return null
    return {
      renew () {
        if ((GM_getValue(key, {}) || {}).owner !== tabId) return false
        GM_setValue(key, { owner: tabId, expires: Date.now() + 45000 })
        return true
      },
      release () {
        if ((GM_getValue(key, {}) || {}).owner === tabId) GM_deleteValue(key)
      }
    }
  }

  function queueBridgeEvent (event) {
    if (!event || !event.submission_id || !PROVIDER_HOSTS[event.provider]) return
    const key = outboxKey(event.submission_id)
    const previous = GM_getValue(key, null)
    if (previous && (TERMINAL_STATUSES.has(previous.status) || previous.timestamp > event.timestamp)) return
    GM_setValue(key, event)
  }

  function scheduleDelivery (id, delay) {
    if (deliveryTimers.has(id)) return
    deliveryTimers.set(id, window.setTimeout(() => {
      deliveryTimers.delete(id)
      flushOutbox(id)
    }, delay))
  }

  function flushOutbox (id) {
    if (window.location.origin !== OJ_ORIGIN || backendEventQueues.has(id)) return backendEventQueues.get(id)
    const event = GM_getValue(outboxKey(id), null)
    if (!event || !currentOjUserId ||
        (event.user_id ? String(event.user_id) !== String(currentOjUserId) : !ownedSubmissionIds.has(id))) return
    const request = Promise.resolve().then(async () => {
      const lease = await acquireLease(id, 'delivery')
      if (!lease) { scheduleDelivery(id, 10000); return }
      try {
        const csrf = cookieValue('csrftoken')
        const headers = { 'Content-Type': 'application/json;charset=UTF-8' }
        if (csrf) headers['X-CSRFToken'] = csrf
        const submission = await ojRequest('/api/remote_submission/event', {
          method: 'POST', headers, body: JSON.stringify(sanitizeBridgePayload(event))
        })
        if (!submission || String(submission.id) !== String(id) ||
            (TERMINAL_STATUSES.has(event.status) && !TERMINAL_STATUSES.has(submission.remote_status))) {
          throw new Error('OJ 尚未确认最终结果')
        }
        deliveryAttempts.delete(id)
        if (TERMINAL_STATUSES.has(submission.remote_status)) {
          GM_deleteValue(outboxKey(id))
          const task = GM_getValue(taskStorageKey(id), null)
          if (task) discardTask(task, true)
        } else if ((GM_getValue(outboxKey(id), {}) || {}).nonce === event.nonce) {
          GM_deleteValue(outboxKey(id))
        }
      } catch (error) {
        const attempt = (deliveryAttempts.get(id) || 0) + 1
        deliveryAttempts.set(id, attempt)
        window.dispatchEvent(new CustomEvent(BRIDGE_EVENT, { detail: {
          schema: TASK_SCHEMA, submission_id: id, provider: event.provider, status: 'SYNC_PENDING',
          message: `结果尚未同步到 OJ，任务已保留并将重试：${error.message}`
        } }))
        scheduleDelivery(id, Math.min(60000, 2000 * (2 ** Math.min(attempt - 1, 5))))
      } finally {
        lease.release()
      }
    }).finally(() => {
      backendEventQueues.delete(id)
      if (GM_getValue(outboxKey(id), null) && !deliveryTimers.has(id)) scheduleDelivery(id, 100)
    })
    backendEventQueues.set(id, request)
    request.catch(() => {})
    return request
  }

  function postBridgeEvent (event) {
    queueBridgeEvent(event)
    return flushOutbox(event.submission_id)
  }

  function dispatchBridgeEvent (event) {
    if (window.location.origin !== OJ_ORIGIN || !event || typeof event !== 'object') return
    if (event.nonce && dispatchedBridgeEvents.has(event.nonce)) return
    if (event.nonce) {
      dispatchedBridgeEvents.add(event.nonce)
      window.setTimeout(() => dispatchedBridgeEvents.delete(event.nonce), 60000)
    }
    window.dispatchEvent(new CustomEvent(BRIDGE_EVENT, { detail: event }))
    postBridgeEvent(event)
  }

  function publishBridgeEvent (task, status, details = {}) {
    const stored = GM_getValue(taskStorageKey(task.submission_id), null)
    if (stored && stored.terminal_event) return stored.terminal_event
    const event = {
      schema: TASK_SCHEMA,
      submission_id: task.submission_id,
      provider: task.provider,
      user_id: task.user_id,
      status,
      timestamp: Date.now(),
      nonce: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      ...sanitizeBridgePayload(details)
    }
    task.status = status
    if (TERMINAL_STATUSES.has(status)) {
      task.terminal_event = event
      delete task.code
    }
    saveTask(task)
    queueBridgeEvent(event)
    GM_setValue(EVENT_STORAGE_KEY, event)
    if (window.location.origin === OJ_ORIGIN) dispatchBridgeEvent(event)
    return event
  }

  function dispatchImportEvent (event) {
    if (window.location.origin !== OJ_ORIGIN || !event || typeof event !== 'object') return
    window.dispatchEvent(new CustomEvent(IMPORT_RESULT_EVENT, { detail: event }))
  }

  function publishImportEvent (task, status, details = {}) {
    const event = {
      schema: IMPORT_SCHEMA,
      request_id: task.request_id,
      provider: task.provider,
      status,
      timestamp: Date.now(),
      nonce: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      ...details
    }
    GM_setValue(IMPORT_EVENT_STORAGE_KEY, event)
    return event
  }

  function normalizeTask (detail) {
    const task = detail && detail.task
    const code = detail && detail.code
    if (!task || task.schema !== TASK_SCHEMA) throw new Error('不支持的远程提交任务版本')
    if (!task.submission_id || !PROVIDER_HOSTS[task.provider]) throw new Error('远程提交任务字段不完整')
    if (!task.remote_submission_id && (typeof code !== 'string' || !code.trim())) throw new Error('提交代码为空')
    if (code && new TextEncoder().encode(code).byteLength > MAX_CODE_SIZE) throw new Error('提交代码超过 1 MiB')

    let targetUrl
    try {
      targetUrl = new URL(task.target_url)
    } catch (error) {
      throw new Error('远程题目地址无效')
    }
    if (targetUrl.protocol !== 'https:' || !PROVIDER_HOSTS[task.provider].has(targetUrl.hostname)) {
      throw new Error('远程题目地址不属于指定平台')
    }
    targetUrl.hash = `xju-oj-remote=${encodeURIComponent(task.submission_id)}`
    return {
      ...task,
      code,
      target_url: targetUrl.toString(),
      stored_at: Date.now()
    }
  }

  function taskIdFromHash () {
    const match = window.location.hash.match(/(?:^#|&)xju-oj-remote=([^&]+)/)
    return match ? decodeURIComponent(match[1]) : ''
  }

  function importTaskIdFromHash () {
    const match = window.location.hash.match(/(?:^#|&)xju-oj-import=([^&]+)/)
    return match ? decodeURIComponent(match[1]) : ''
  }

  function loadProviderTask (provider) {
    // Luogu changes #xju-oj-remote=... into #submit for native verification.
    // Keep the identity in this tab so another submission cannot replace it.
    let boundId = ''
    try { boundId = window.sessionStorage.getItem(`${STORAGE_PREFIX}:bound:${provider}`) || '' } catch (_) {}
    const taskId = taskIdFromHash() || boundId || GM_getValue(activeTaskStorageKey(provider), '')
    if (!taskId) return null
    const task = GM_getValue(taskStorageKey(taskId), null)
    if (!task || task.provider !== provider || task.schema !== TASK_SCHEMA) return null
    try { window.sessionStorage.setItem(`${STORAGE_PREFIX}:bound:${provider}`, taskId) } catch (_) {}
    return task
  }

  function saveTask (task) {
    GM_setValue(taskStorageKey(task.submission_id), task)
  }

  function openProviderActionTab (task, status, message, details = {}) {
    if (status !== 'AUTH_REQUIRED' && status !== 'VERIFICATION_REQUIRED') {
      throw new Error(`不允许为 ${status} 状态打开外部标签页`)
    }
    if (!task.remote_submission_id && ['SUBMITTING', 'SUBMIT_UNCERTAIN'].includes((task.adapter_state || {}).phase)) {
      task.adapter_state = { phase: 'NEEDS_ACTION' }
    }
    const now = Date.now()
    const previous = task.action_tab || {}
    if (previous.status === status && now - Number(previous.opened_at || 0) < 10000) {
      publishBridgeEvent(task, status, { message, ...details })
      return
    }
    task.action_tab = { status, opened_at: now }
    saveTask(task)
    publishBridgeEvent(task, status, { message, ...details })
    const backgroundCloudflare = task.provider === 'CODEFORCES' &&
      status === 'VERIFICATION_REQUIRED' &&
      details.verification_source === 'codeforces-cloudflare'
    GM_openInTab(task.target_url, {
      active: !backgroundCloudflare,
      insert: true,
      setParent: true
    })
  }

  function openProviderRetryTab (task, message) {
    const now = Date.now()
    const previous = task.action_tab || {}
    if (previous.status === 'OPENING' && now - Number(previous.opened_at || 0) < 10000) return
    task.action_tab = { status: 'OPENING', opened_at: now }
    saveTask(task)
    publishBridgeEvent(task, 'OPENING', { message })
    GM_openInTab(task.target_url, {
      active: true,
      insert: true,
      setParent: true
    })
  }

  function codeforcesImportTarget (reference) {
    const value = String(reference || '').trim()
    let match
    if (value.includes('://')) {
      const parsed = new URL(value)
      if (!PROVIDER_HOSTS.CODEFORCES.has(parsed.hostname)) throw new Error('只支持 Codeforces 题目链接')
      match = parsed.pathname.match(/\/(?:problemset\/problem|contest)\/(\d+)\/(?:problem\/)?([A-Za-z][A-Za-z0-9]*)\/?$/)
    } else {
      match = value.match(/^(\d+)[\s\-_/]*([A-Za-z][A-Za-z0-9]*)$/)
    }
    if (!match) throw new Error('Codeforces 题号应类似 4A')
    const contestId = match[1]
    const index = match[2].toUpperCase()
    return {
      contest_id: contestId,
      index,
      target_url: `https://codeforces.com/problemset/problem/${contestId}/${index}`
    }
  }

  function normalizeImportTask (detail) {
    if (!detail || detail.schema !== IMPORT_SCHEMA || detail.provider !== 'CODEFORCES' || !detail.request_id) {
      throw new Error('远程导题任务无效')
    }
    const target = codeforcesImportTarget(detail.reference)
    const targetUrl = new URL(target.target_url)
    targetUrl.hash = `xju-oj-import=${encodeURIComponent(detail.request_id)}`
    return {
      ...detail,
      ...target,
      target_url: targetUrl.toString(),
      stored_at: Date.now()
    }
  }

  function clearActiveTask (task) {
    if (GM_getValue(activeTaskStorageKey(task.provider), '') === task.submission_id) {
      GM_deleteValue(activeTaskStorageKey(task.provider))
    }
  }

  function discardTask (task, acknowledged = false) {
    clearActiveTask(task)
    if (!acknowledged && GM_getValue(outboxKey(task.submission_id), null)) return
    GM_deleteValue(taskStorageKey(task.submission_id))
  }

  function sleep (milliseconds) {
    return new Promise(resolve => window.setTimeout(resolve, milliseconds))
  }

  function returnToOj (task) {
    clearActiveTask(task)
    if (window.location.origin === OJ_ORIGIN) {
      window.focus()
      return
    }
    window.setTimeout(() => {
      try {
        if (window.opener) window.opener.focus()
        window.close()
      } catch (error) {}
    }, 800)
  }

  function handOffJudgingToOj () {
    if (window.location.origin === OJ_ORIGIN) return
    window.setTimeout(() => {
      try {
        if (window.opener) window.opener.focus()
        window.close()
      } catch (error) {}
    }, 500)
  }

  function returnImportToOj () {
    window.setTimeout(() => {
      try {
        if (window.opener) window.opener.focus()
        window.close()
      } catch (error) {}
    }, 500)
  }

  function codeforcesChallengeVisible (root = document, html = '') {
    const title = String(root.title || '').toLowerCase()
    const source = String(html || '').toLowerCase()
    return title.includes('just a moment') ||
      Boolean(root.querySelector(
        '[id^="challenge-"], #challenge-form, form[action*="/cdn-cgi/challenge"], ' +
        'iframe[src*="challenges.cloudflare.com"]'
      )) ||
      source.includes('window._cf_chl_opt') || source.includes('cf-chl-')
  }

  function codeforcesHandle (root = document, pathname = window.location.pathname) {
    const anchors = root.querySelectorAll('#header a[href^="/profile/"]')
    for (const anchor of anchors) {
      const match = anchor.getAttribute('href').match(/^\/profile\/([^/?#]+)/)
      if (match && match[1]) return decodeURIComponent(match[1])
    }
    const submissionMatch = String(pathname || '').match(/^\/submissions\/([^/?#]+)/)
    return submissionMatch ? decodeURIComponent(submissionMatch[1]) : ''
  }

  async function codeforcesSubmissions (handle, from = 1) {
    const url = new URL('/api/user.status', 'https://codeforces.com')
    url.searchParams.set('handle', handle)
    url.searchParams.set('from', String(from))
    url.searchParams.set('count', '100')
    const payload = await gmJsonRequest('GET', url.toString())
    if (payload.status !== 'OK' || !Array.isArray(payload.result)) {
      throw new Error(payload.comment || 'Codeforces API 请求失败')
    }
    return payload.result
  }

  function findCodeforcesRun (runs, task) {
    if (task.remote_submission_id) return runs.find(run => String(run.id) === String(task.remote_submission_id))
    const providerData = task.provider_data || {}
    const contestId = Number(providerData.contest_id)
    const index = String(providerData.index || '').toUpperCase()
    const beforeId = Number((task.adapter_state || {}).before_id || 0)
    const startedAt = Number((task.adapter_state || {}).started_at || 0)
    return runs.find(run => {
      const problem = run.problem || {}
      return Number(run.id) > beforeId &&
        Number(problem.contestId) === contestId &&
        String(problem.index || '').toUpperCase() === index &&
        Number(run.creationTimeSeconds || 0) >= startedAt - 10
    })
  }

  async function pollCodeforcesRun (task) {
    const state = task.adapter_state || {}
    const deadline = Date.now() + 120000
    let submittedEventSent = Boolean(task.remote_submission_id)
    let successfulPolls = 0
    let connectionFailures = 0
    while (Date.now() < deadline && pollingActive(task)) {
      let runs
      try {
        runs = await codeforcesSubmissions(state.handle, state.lookup_from || 1)
        successfulPolls += 1
      } catch (error) {
        if (isRemoteConnectionError(error)) connectionFailures += 1
        const challengeResponse = error && error.response
        const challengeDocument = challengeResponse
          ? new DOMParser().parseFromString(challengeResponse.responseText || '', 'text/html')
          : null
        if (codeforcesChallengeVisible() || (challengeDocument && codeforcesChallengeVisible(
          challengeDocument,
          challengeResponse.responseText
        ))) {
          if (window.location.origin === OJ_ORIGIN) {
            openProviderActionTab(
              task,
              'VERIFICATION_REQUIRED',
              '请在 Codeforces 页面完成 Cloudflare 人机验证',
              { verification_source: 'codeforces-cloudflare' }
            )
          } else {
            publishBridgeEvent(task, 'VERIFICATION_REQUIRED', {
              message: '请在 Codeforces 页面完成 Cloudflare 人机验证',
              verification_source: 'codeforces-cloudflare'
            })
          }
          return
        }
        await sleep(2000)
        continue
      }
      const run = findCodeforcesRun(runs, task)
      if (!run) {
        if (task.remote_submission_id && runs.length === 100 &&
            Number(runs[runs.length - 1].id) > Number(task.remote_submission_id)) {
          state.lookup_from = (state.lookup_from || 1) + 100
          task.adapter_state = state
          saveTask(task)
        }
        await sleep(2200)
        continue
      }

      task.remote_submission_id = String(run.id)
      task.adapter_state = { ...state, phase: 'JUDGING' }
      delete task.code
      saveTask(task)
      const remoteUrl = `https://codeforces.com/contest/${run.contestId}/submission/${run.id}`
      if (!submittedEventSent) {
        submittedEventSent = true
        publishBridgeEvent(task, 'SUBMITTED', {
          remote_submission_id: task.remote_submission_id,
          remote_url: remoteUrl,
          message: 'Codeforces 已接收提交'
        })
        publishBridgeEvent(task, 'JUDGING', {
          remote_submission_id: task.remote_submission_id,
          remote_url: remoteUrl,
          message: 'Codeforces 正在判题'
        })
      }

      if (run.verdict && run.verdict !== 'TESTING') {
        publishBridgeEvent(task, 'FINISHED', {
          remote_submission_id: task.remote_submission_id,
          remote_url: remoteUrl,
          verdict: run.verdict,
          time_ms: Number(run.timeConsumedMillis || 0),
          memory_bytes: Number(run.memoryConsumedBytes || 0),
          passed_tests: Number(run.passedTestCount || 0),
          message: String(run.testset || run.phase || run.verdict),
          verification_source: 'codeforces-api'
        })
        returnToOj(task)
        return
      }
      if (window.location.origin !== OJ_ORIGIN) {
        handOffJudgingToOj()
        return
      }
      await sleep(2200)
    }

    if (!pollingActive(task)) return
    if (task.remote_submission_id) {
      publishBridgeEvent(task, 'JUDGING', {
        remote_submission_id: task.remote_submission_id,
        message: 'Codeforces 判题时间较长，请保留此标签页或稍后查看提交记录'
      })
    } else if (!successfulPolls && connectionFailures) {
      publishBridgeEvent(task, 'OPENING', {
        message: '暂时无法连接 Codeforces 官方 API，提交任务已保留并将在稍后重试'
      })
      if (window.location.origin === OJ_ORIGIN) {
        window.setTimeout(() => resumeOjJudgingTask(task), 4000)
      } else {
        window.setTimeout(() => pollCodeforcesRun(task), 4000)
      }
    } else if (state.connection_uncertain) {
      publishBridgeEvent(task, 'OPENING', {
        message: 'Codeforces 暂未找到提交记录，将继续查询；请核对原站记录，避免重复提交代码'
      })
    } else {
      publishBridgeEvent(task, 'FAILED', {
        message: 'Codeforces 官方 API 中没有找到本次提交，请先检查账号提交记录再重试'
      })
      discardTask(task)
    }
  }

  function codeforcesSubmitForm (root = document) {
    return Array.from(root.forms).find(form => {
      return form.querySelector('[name="programTypeId"]') &&
        form.querySelector('[name="sourceFile"], [name="source"]')
    }) || null
  }

  function codeforcesSubmitBody (form, task) {
    const language = form.querySelector('[name="programTypeId"]')
    const option = language && Array.from(language.options).find(item => item.value === String(task.language_id))
    if (!language || !option) throw new Error(`Codeforces 当前页面不支持语言 ID ${task.language_id}`)

    const body = new FormData(form)
    body.set(language.name || 'programTypeId', String(task.language_id))
    const nonceLength = Math.floor(Date.now() / 1000) % 97 + 1
    const source = `${task.code.replace(/\s+$/, '')}\n${' '.repeat(nonceLength)}\n`
    const fileInput = form.querySelector('input[type="file"][name="sourceFile"]')
    if (fileInput) {
      body.delete(fileInput.name)
      body.append(fileInput.name, new File([source], 'main.txt', { type: 'text/plain' }))
    } else {
      const textarea = form.querySelector('textarea[name="source"], [name="source"]')
      if (!textarea || !textarea.name) throw new Error('Codeforces 提交表单中没有源码字段')
      body.set(textarea.name, source)
    }
    const submitter = form.querySelector('button[type="submit"][name], input[type="submit"][name]')
    if (submitter && submitter.name) body.set(submitter.name, submitter.value || '')
    return body
  }

  function fillCodeforcesForm (form, task) {
    const language = form.querySelector('[name="programTypeId"]')
    const option = language && Array.from(language.options).find(item => item.value === String(task.language_id))
    if (!language || !option) throw new Error(`Codeforces 当前页面不支持语言 ID ${task.language_id}`)
    language.value = String(task.language_id)
    language.dispatchEvent(new Event('change', { bubbles: true }))

    const nonceLength = Math.floor(Date.now() / 1000) % 97 + 1
    const source = `${task.code.replace(/\s+$/, '')}\n${' '.repeat(nonceLength)}\n`
    const fileInput = form.querySelector('input[type="file"][name="sourceFile"]')
    if (fileInput) {
      const transfer = new DataTransfer()
      transfer.items.add(new File([source], 'main.txt', { type: 'text/plain' }))
      fileInput.files = transfer.files
      fileInput.dispatchEvent(new Event('change', { bubbles: true }))
      return
    }
    const textarea = form.querySelector('textarea[name="source"], [name="source"]')
    if (!textarea) throw new Error('Codeforces 提交表单中没有源码字段')
    textarea.value = source
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    textarea.dispatchEvent(new Event('change', { bubbles: true }))
  }

  async function bootCodeforcesTask (task) {
    if (codeforcesChallengeVisible()) {
      publishBridgeEvent(task, 'VERIFICATION_REQUIRED', {
        message: '请在当前标签页完成 Codeforces Cloudflare 人机验证'
      })
      return
    }

    const state = task.adapter_state || {}
    if (state.phase === 'AWAITING_ID' || state.phase === 'JUDGING') {
      task.status = 'JUDGING'
      saveTask(task)
      await resumeOjJudgingTask(task)
      return
    }

    const handle = codeforcesHandle()
    if (!handle) {
      publishBridgeEvent(task, 'AUTH_REQUIRED', {
        message: '请先登录 Codeforces，登录成功后脚本会返回题目并继续提交'
      })
      if (!window.location.pathname.startsWith('/enter')) {
        const back = new URL(task.target_url)
        back.hash = ''
        window.location.assign(`/enter?back=${encodeURIComponent(back.pathname + back.search)}`)
      }
      return
    }

    const providerData = task.provider_data || {}
    const expectedPath = `/problemset/problem/${providerData.contest_id}/${providerData.index}`
    if (!window.location.pathname.includes(`/problem/${providerData.contest_id}/${providerData.index}`) &&
        window.location.pathname !== expectedPath) {
      window.location.replace(task.target_url)
      return
    }

    const form = codeforcesSubmitForm()
    if (!form) {
      publishBridgeEvent(task, 'AUTH_REQUIRED', {
        message: 'Codeforces 页面没有提交表单，请确认账号已登录且题目允许提交'
      })
      return
    }

    try {
      const runs = await codeforcesSubmissions(handle)
      fillCodeforcesForm(form, task)
      task.adapter_state = {
        phase: 'AWAITING_ID',
        handle,
        before_id: runs.reduce((maximum, run) => Math.max(maximum, Number(run.id || 0)), 0),
        started_at: Math.floor(Date.now() / 1000)
      }
      saveTask(task)
      publishBridgeEvent(task, 'OPENING', { message: '正在通过 Codeforces 原生表单提交代码' })
      const submitter = form.querySelector('button[type="submit"], input[type="submit"]')
      if (typeof form.requestSubmit === 'function' && submitter) form.requestSubmit(submitter)
      else if (typeof form.requestSubmit === 'function') form.requestSubmit()
      else if (submitter) submitter.click()
      else form.submit()
      window.setTimeout(() => resumeOjJudgingTask(task), 1200)
    } catch (error) {
      if (isRemoteConnectionError(error)) {
        publishBridgeEvent(task, 'OPENING', {
          message: '暂时无法连接 Codeforces，任务已保留并将在当前页面重试'
        })
        window.setTimeout(() => bootCodeforcesTask(task), 4000)
      } else {
        publishBridgeEvent(task, 'FAILED', { message: error.message || 'Codeforces 提交失败' })
        discardTask(task)
      }
    }
  }

  async function bootCodeforcesImport (task) {
    if (codeforcesChallengeVisible()) {
      publishImportEvent(task, 'VERIFICATION_REQUIRED', {
        message: '请在当前标签页完成 Codeforces Cloudflare 验证，随后将自动继续导题'
      })
      return
    }
    const expectedPath = `/problemset/problem/${task.contest_id}/${task.index}`
    if (!window.location.pathname.includes(`/problem/${task.contest_id}/${task.index}`) &&
        window.location.pathname !== expectedPath) {
      window.location.replace(task.target_url)
      return
    }
    const statement = document.querySelector('.problem-statement')
    if (!statement) {
      publishImportEvent(task, 'FAILED', { message: 'Codeforces 页面中没有找到题面' })
      return
    }
    publishImportEvent(task, 'FINISHED', {
      page_html: statement.outerHTML,
      canonical_reference: `${task.contest_id}${task.index}`
    })
    GM_deleteValue(importTaskStorageKey(task.request_id))
    if (GM_getValue(activeImportStorageKey(task.provider), '') === task.request_id) {
      GM_deleteValue(activeImportStorageKey(task.provider))
    }
    returnImportToOj()
  }

  function gmRawRequest (method, url, data = null, headers = {}) {
    return new Promise((resolve, reject) => {
      const rejectConnection = (message, response) => {
        const requestError = new Error(message)
        requestError.remoteConnection = true
        if (response) requestError.response = response
        reject(requestError)
      }
      GM_xmlhttpRequest({
        method,
        url,
        data: data === null ? undefined : data,
        headers,
        timeout: 30000,
        withCredentials: true,
        onload: resolve,
        onerror: response => rejectConnection('无法连接远程平台', response),
        ontimeout: response => rejectConnection('连接远程平台超时', response)
      })
    })
  }

  function isRemoteConnectionError (error) {
    return Boolean(error && error.remoteConnection)
  }

  function responseJson (response) {
    try {
      return JSON.parse(response.responseText || '{}')
    } catch (error) {
      const requestError = new Error('远程平台返回了无法解析的数据')
      requestError.response = response
      requestError.status = response.status
      throw requestError
    }
  }

  async function gmJsonRequest (method, url, body = null, headers = {}) {
    const requestHeaders = {
      Accept: 'application/json, text/plain, */*'
    }
    if (body !== null) requestHeaders['Content-Type'] = 'application/json;charset=UTF-8'
    Object.assign(requestHeaders, headers)
    const response = await gmRawRequest(
      method,
      url,
      body === null ? null : JSON.stringify(body),
      requestHeaders
    )
    const payload = responseJson(response)
    if (response.status < 200 || response.status >= 300) {
      const requestError = new Error(payload.msg || payload.message || `HTTP ${response.status}`)
      requestError.payload = payload
      requestError.status = response.status
      requestError.response = response
      throw requestError
    }
    return payload
  }

  function codeforcesVerificationVisible (root, html = '') {
    return codeforcesChallengeVisible(root, html) || Boolean(root.querySelector(
      '#challenge-form iframe[src*="recaptcha"], #challenge-form iframe[src*="turnstile"], ' +
      'form[action*="/cdn-cgi/challenge"] iframe'
    ))
  }

  function codeforcesCaptchaMessage (root) {
    const error = root.querySelector('.error[for], .alert-danger, .notice.error')
    const message = String((error && error.textContent) || '').trim()
    return /captcha|verification|verify|robot|human|验证码|人机|验证/i.test(message)
      ? message
      : ''
  }

  async function submitCodeforcesFromOj (task) {
    const target = new URL(task.target_url)
    target.hash = ''
    const pageResponse = await gmRawRequest('GET', target.toString(), null, {
      Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    })
    const pageHtml = pageResponse.responseText || ''
    const page = new DOMParser().parseFromString(pageHtml, 'text/html')
    if (codeforcesVerificationVisible(page, pageHtml)) {
      openProviderActionTab(
        task,
        'VERIFICATION_REQUIRED',
        '请在 Codeforces 页面完成 Cloudflare 人机验证',
        { verification_source: 'codeforces-cloudflare' }
      )
      return
    }

    const finalUrl = new URL(pageResponse.finalUrl || target.toString())
    const handle = codeforcesHandle(page, finalUrl.pathname)
    if (!handle || finalUrl.pathname.startsWith('/enter')) {
      openProviderActionTab(task, 'AUTH_REQUIRED', 'Codeforces 登录状态已失效，请重新登录')
      return
    }
    if (pageResponse.status < 200 || pageResponse.status >= 300) {
      throw new Error(`Codeforces 题目页返回 HTTP ${pageResponse.status}`)
    }

    const form = codeforcesSubmitForm(page)
    if (!form) throw new Error('Codeforces 题目页没有可用的提交表单')
    const runs = await codeforcesSubmissions(handle)
    const body = codeforcesSubmitBody(form, task)
    const action = new URL(form.getAttribute('action') || finalUrl.toString(), finalUrl)
    const state = {
      phase: 'AWAITING_ID',
      handle,
      before_id: runs.reduce((maximum, run) => Math.max(maximum, Number(run.id || 0)), 0),
      started_at: Math.floor(Date.now() / 1000)
    }
    task.adapter_state = { ...state, connection_uncertain: true }
    saveTask(task)
    const submitResponse = await gmRawRequest('POST', action.toString(), body, {
      Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      Origin: 'https://codeforces.com',
      Referer: finalUrl.toString()
    })
    const submitHtml = submitResponse.responseText || ''
    const submitPage = new DOMParser().parseFromString(submitHtml, 'text/html')
    if (codeforcesVerificationVisible(submitPage, submitHtml)) {
      openProviderActionTab(
        task,
        'VERIFICATION_REQUIRED',
        'Codeforces 要求完成人机验证后才能提交',
        { verification_source: 'codeforces-submit' }
      )
      return
    }
    const submitUrl = new URL(submitResponse.finalUrl || action.toString())
    if (submitUrl.pathname.startsWith('/enter')) {
      openProviderActionTab(task, 'AUTH_REQUIRED', 'Codeforces 登录状态已失效，请重新登录')
      return
    }
    if (submitResponse.status < 200 || submitResponse.status >= 300) {
      throw new Error(`Codeforces 提交接口返回 HTTP ${submitResponse.status}`)
    }
    const captchaMessage = codeforcesCaptchaMessage(submitPage)
    if (captchaMessage) {
      openProviderActionTab(
        task,
        'VERIFICATION_REQUIRED',
        captchaMessage,
        { verification_source: 'codeforces-submit' }
      )
      return
    }
    const formError = submitPage.querySelector('.error[for], .alert-danger, .notice.error')
    if (formError && String(formError.textContent || '').trim()) {
      throw new Error(`Codeforces 提交失败：${String(formError.textContent || '').trim()}`)
    }

    task.adapter_state = state
    saveTask(task)
    publishBridgeEvent(task, 'OPENING', { message: 'Codeforces 已接收请求，正在定位提交记录' })
    await resumeOjJudgingTask(task)
  }

  function nowcoderVerificationRequired (payload) {
    const message = String((payload && (payload.msg || payload.message)) || '').toLowerCase()
    return message.includes('验证') || message.includes('captcha') || message.includes('安全') || message.includes('风控')
  }

  function nowcoderAuthRequired (payload) {
    const message = String((payload && (payload.msg || payload.message)) || '').toLowerCase()
    return message.includes('登录') || message.includes('未授权') || message.includes('token')
  }

  async function nowcoderAccountContext (referer) {
    const payload = await gmJsonRequest(
      'GET',
      'https://www.nowcoder.com/profile/user-info-v2',
      null,
      { Referer: referer }
    )
    const account = payload && payload.data
    if (!account || !account.userId || (payload.code !== 0 && payload.code !== '0')) {
      throw new Error(payload.msg || '牛客账号尚未登录')
    }
    return {
      user_id: Number(account.userId),
      app_id: account.isMember ? 9 : 5,
      account: String(account.userId)
    }
  }

  async function nowcoderAccessToken (referer) {
    const payload = await gmJsonRequest(
      'GET',
      'https://gw-c.nowcoder.com/api/sparta/base-oauth/access-token?sceneType=1',
      null,
      { Referer: referer }
    )
    const token = payload && payload.data && payload.data.accessToken
    if (!payload.success || !token) throw new Error(payload.msg || '牛客判题 Token 获取失败')
    return String(token)
  }

  function nowcoderQueryUrl (state) {
    const url = new URL('https://victorinox.nowcoder.com/api/service/judge/submit-status')
    const params = {
      userId: state.user_id,
      appId: state.app_id,
      tagId: state.tag_id,
      id: state.submission_id,
      submissionId: state.submission_id,
      submitType: 1,
      token: state.token,
      remark: ''
    }
    Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, String(value)))
    return url.toString()
  }

  async function pollNowcoderRun (task) {
    const deadline = Date.now() + 120000
    let refreshedToken = false
    while (Date.now() < deadline && pollingActive(task)) {
      const state = task.adapter_state || {}
      try {
        const payload = await gmJsonRequest(
          'GET',
          nowcoderQueryUrl(state),
          null,
          { Referer: state.referer || task.target_url.split('#')[0] }
        )
        if (nowcoderVerificationRequired(payload)) {
          const message = payload.msg || '请在牛客页面完成验证后继续查询结果'
          if (window.location.origin === OJ_ORIGIN) openProviderActionTab(task, 'VERIFICATION_REQUIRED', message)
          else publishBridgeEvent(task, 'VERIFICATION_REQUIRED', { message })
          return
        }
        if (nowcoderAuthRequired(payload)) {
          if (!refreshedToken) {
            refreshedToken = true
            await refreshNowcoderQueryState(task)
            continue
          }
          const message = payload.msg || '牛客登录状态已失效'
          if (window.location.origin === OJ_ORIGIN) openProviderActionTab(task, 'AUTH_REQUIRED', message)
          else publishBridgeEvent(task, 'AUTH_REQUIRED', { message })
          return
        }
        const result = payload && payload.data
        if (!result || (payload.code !== 0 && payload.code !== '0' && payload.code !== undefined)) {
          await sleep(1200)
          continue
        }
        const status = Number(result.status || 0)
        if (status >= 3) {
          publishBridgeEvent(task, 'FINISHED', {
            remote_submission_id: String(state.submission_id),
            remote_url: task.target_url.split('#')[0],
            verdict: String(result.judgeReplyDesc || result.judgeReply || result.desc || `STATUS_${status}`),
            time_ms: Number(result.timeConsumption || 0),
            memory_bytes: Number(result.memoryConsumption || 0) * 1024,
            passed_tests: Number(result.rightCaseNum || 0),
            total_tests: Number(result.allCaseNum || 0),
            score: result.rightHundredRate,
            message: String(result.memo || result.judgeReplyDesc || ''),
            verification_source: 'nowcoder-session-api'
          })
          returnToOj(task)
          return
        }
      } catch (error) {
        if (nowcoderAuthRequired(error.payload) || error.status === 401 || String(error.message).includes('登录')) {
          if (!refreshedToken) {
            refreshedToken = true
            try { await refreshNowcoderQueryState(task); continue } catch (_) {}
          }
          const message = error.message || '牛客登录状态已失效'
          if (window.location.origin === OJ_ORIGIN) openProviderActionTab(task, 'AUTH_REQUIRED', message)
          else publishBridgeEvent(task, 'AUTH_REQUIRED', { message })
          return
        }
        if (nowcoderVerificationRequired(error.payload) || error.status === 403) {
          const message = '请在牛客页面完成验证后继续查询结果'
          if (window.location.origin === OJ_ORIGIN) openProviderActionTab(task, 'VERIFICATION_REQUIRED', message)
          else publishBridgeEvent(task, 'VERIFICATION_REQUIRED', { message })
          return
        }
      }
      await sleep(1200)
    }
    if (!pollingActive(task)) return
    publishBridgeEvent(task, 'JUDGING', {
      remote_submission_id: String((task.adapter_state || {}).submission_id || ''),
      message: '牛客判题时间较长，请保留此标签页或稍后查看提交记录'
    })
  }

  function acceptNowcoderSubmission (task, submitBody, responsePayload) {
    if (nowcoderAuthRequired(responsePayload) || nowcoderVerificationRequired(responsePayload) ||
        (responsePayload.code !== undefined && ![0, '0'].includes(responsePayload.code))) return
    const result = responsePayload && responsePayload.data
    const submissionId = result && (result.id || result.submissionId)
    if (!submissionId) throw new Error(responsePayload.msg || '牛客没有返回提交 ID')
    if (task.remote_submission_id || task.terminal_event) return
    task.remote_submission_id = String(submissionId)
    task.adapter_state = {
      phase: 'JUDGING',
      user_id: Number(submitBody.userId),
      app_id: Number(submitBody.appId),
      tag_id: Number(submitBody.tagId || 0),
      token: String(submitBody.token),
      submission_id: String(submissionId),
      referer: task.target_url.split('#')[0]
    }
    delete task.code
    saveTask(task)
    publishBridgeEvent(task, 'SUBMITTED', {
      remote_submission_id: String(submissionId),
      remote_url: task.target_url.split('#')[0],
      message: '牛客已接收提交'
    })
    publishBridgeEvent(task, 'JUDGING', {
      remote_submission_id: String(submissionId),
      remote_url: task.target_url.split('#')[0],
      message: '牛客正在判题'
    })
    handOffJudgingToOj()
  }

  function nativeSubmissionTask (provider, requestPath, payload) {
    const task = provider === 'NOWCODER' ? unsafeWindow.__xjuOjRemoteBridgeNowcoderTask
      : unsafeWindow.__xjuOjRemoteBridgeLuoguTask
    if (!task || task.remote_submission_id || task.terminal_event || typeof task.code !== 'string') return null
    if (provider === 'NOWCODER') {
      const expected = String((task.provider_data || {}).question_id || '')
      if (!expected || String((payload || {}).questionId || '') !== expected) return null
    } else {
      const problemId = (task.provider_data || {}).problem_id || task.problem_id
      if (requestPath !== `/fe/api/problem/submit/${encodeURIComponent(problemId)}`) return null
    }
    return task
  }

  function installNowcoderXhrInterceptor (task) {
    const Xhr = unsafeWindow.XMLHttpRequest
    if (!Xhr) return
    unsafeWindow.__xjuOjRemoteBridgeNowcoderTask = task
    if (Xhr.prototype.__xjuOjRemoteBridgePatched) return
    Xhr.prototype.__xjuOjRemoteBridgePatched = true
    const originalOpen = Xhr.prototype.open
    const originalSend = Xhr.prototype.send
    Xhr.prototype.open = function (method, url, ...rest) {
      this.__xjuOjRemoteUrl = String(url || '')
      return originalOpen.call(this, method, url, ...rest)
    }
    Xhr.prototype.send = function (body) {
      let requestPath = ''
      try {
        requestPath = new URL(this.__xjuOjRemoteUrl, window.location.origin).pathname
      } catch (error) {}
      let outgoingBody = body
      if (requestPath.endsWith('/api/service/judge/submit')) {
        let submitBody = null
        let activeTask = null
        try {
          submitBody = typeof body === 'string' ? JSON.parse(body) : body
          activeTask = nativeSubmissionTask('NOWCODER', requestPath, submitBody)
          if (activeTask && submitBody && typeof submitBody === 'object' && !(submitBody instanceof FormData)) {
            submitBody.content = activeTask.code
            submitBody.language = String(activeTask.language_id)
            outgoingBody = typeof body === 'string' ? JSON.stringify(submitBody) : submitBody
          }
        } catch (error) {}
        this.addEventListener('load', () => {
          try {
            const responsePayload = JSON.parse(this.responseText || '{}')
            if (activeTask && submitBody && responsePayload && responsePayload.data) {
              acceptNowcoderSubmission(activeTask, submitBody, responsePayload)
            }
          } catch (error) {}
        }, { once: true })
      }
      return originalSend.call(this, outgoingBody)
    }

    const originalFetch = unsafeWindow.fetch
    if (originalFetch && !originalFetch.__xjuOjRemoteBridgeNowcoderPatched) {
      const patchedFetch = async function (input, init = {}) {
        let requestPath = ''
        try {
          requestPath = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname
        } catch (error) {}
        let outgoingInit = init
        let submitBody = null
        let activeTask = null
        if (requestPath.endsWith('/api/service/judge/submit')) {
          try {
            submitBody = typeof init.body === 'string' ? JSON.parse(init.body) : init.body
            activeTask = nativeSubmissionTask('NOWCODER', requestPath, submitBody)
            if (activeTask && submitBody && typeof submitBody === 'object' && !(submitBody instanceof FormData)) {
              submitBody.content = activeTask.code
              submitBody.language = String(activeTask.language_id)
              submitBody.questionId = String((activeTask.provider_data || {}).question_id || submitBody.questionId || '')
              outgoingInit = { ...init, body: typeof init.body === 'string' ? JSON.stringify(submitBody) : submitBody }
            }
          } catch (error) {}
        }
        const response = await originalFetch.call(this, input, outgoingInit)
        if (requestPath.endsWith('/api/service/judge/submit') && submitBody) {
          response.clone().json().then(payload => {
            if (activeTask && payload && payload.data) acceptNowcoderSubmission(activeTask, submitBody, payload)
          }).catch(() => {})
        }
        return response
      }
      patchedFetch.__xjuOjRemoteBridgeNowcoderPatched = true
      unsafeWindow.fetch = patchedFetch
    }
  }

  async function prepareNowcoderNativeVerification (task, message) {
    installNowcoderXhrInterceptor(task)
    publishBridgeEvent(task, 'VERIFICATION_REQUIRED', {
      message: message || '请在牛客原生页面完成人机验证'
    })

    const deadline = Date.now() + 15000
    while (Date.now() < deadline) {
      const monaco = unsafeWindow.monaco
      const models = monaco && monaco.editor && monaco.editor.getModels()
      const codeMirrorNode = document.querySelector('#jsCodeEditor .CodeMirror, .answer-module .CodeMirror')
      const codeMirror = codeMirrorNode && codeMirrorNode.CodeMirror
      const submitter = document.querySelector('.btn-submit, .submit-btnbox button, button[class*="submit"]')
      if (((models && models.length) || codeMirror) && submitter) {
        if (models && models.length) models[0].setValue(task.code)
        else codeMirror.setValue(task.code)
        submitter.click()
        return
      }
      await sleep(300)
    }
  }

  async function requestNowcoderVerification (task, message) {
    if (!task.remote_submission_id) { task.adapter_state = { phase: 'NEEDS_ACTION' }; saveTask(task) }
    if (window.location.origin === OJ_ORIGIN) {
      openProviderActionTab(
        task,
        'VERIFICATION_REQUIRED',
        message || '请在牛客原生页面完成人机验证',
        { verification_source: 'nowcoder-submit' }
      )
      return
    }
    await prepareNowcoderNativeVerification(task, message)
  }

  async function submitNowcoderDirect (task) {
    const providerData = task.provider_data || {}
    const pageInfo = unsafeWindow.pageInfo || {}
    const questionId = providerData.question_id || pageInfo.questionId
    if (!questionId) throw new Error('牛客题目缺少 questionId')
    const referer = task.target_url.split('#')[0]
    const account = await nowcoderAccountContext(referer)
    const token = await nowcoderAccessToken(referer)
    const body = {
      content: task.code,
      questionId: String(questionId),
      language: String(task.language_id),
      submitType: 1,
      tagId: Number(providerData.tag_id || pageInfo.tagId || 0),
      appId: account.app_id,
      userId: account.user_id,
      remark: '',
      token
    }
    const payload = await sendProviderCode(task, () => gmJsonRequest(
      'POST',
      'https://victorinox.nowcoder.com/api/service/judge/submit',
      body,
      { Referer: referer, Origin: 'https://www.nowcoder.com' }
    ))
    if (nowcoderVerificationRequired(payload)) {
      await requestNowcoderVerification(task, payload.msg)
      return false
    }
    if (nowcoderAuthRequired(payload)) throw new Error(payload.msg || '牛客登录状态已失效')
    if (payload.code !== 0 && payload.code !== '0' && payload.code !== undefined) {
      throw new Error(payload.msg || `牛客提交失败，code=${payload.code}`)
    }
    acceptNowcoderSubmission(task, body, payload)
    return true
  }

  async function bootNowcoderTask (task) {
    const state = task.adapter_state || {}
    if (state.phase === 'JUDGING' && state.submission_id) {
      await restoreRemoteQuery(task)
      return
    }

    const isLogin = unsafeWindow.isLogin
    if (isLogin === false || document.querySelector('#nav-login, .nav-account-login')) {
      publishBridgeEvent(task, 'AUTH_REQUIRED', {
        message: '请先登录牛客，登录成功后脚本会继续提交'
      })
      if (!window.location.pathname.startsWith('/login')) {
        const callback = new URL(task.target_url)
        callback.hash = ''
        window.location.assign(`/login?callBack=${encodeURIComponent(callback.toString())}`)
      }
      return
    }

    const target = new URL(task.target_url)
    const isAcmProblem = target.hostname === 'ac.nowcoder.com' && target.pathname.includes('/acm/problem/')
    const expectedProblemId = String((task.provider_data || {}).problem_id || '').replace(/^NC/i, '')
    if (isAcmProblem && expectedProblemId && !window.location.pathname.includes(`/acm/problem/${expectedProblemId}`)) {
      window.location.replace(task.target_url)
      return
    }
    if (!isAcmProblem) {
      publishBridgeEvent(task, 'FAILED', {
        message: '当前脚本只支持 ac.nowcoder.com/acm/problem 题目，请由管理员用 NC 题号重新导入'
      })
      discardTask(task)
      return
    }

    try {
      await submitNowcoderDirect(task)
    } catch (error) {
      if (error.submitUncertain) return
      const message = error.message || '牛客提交失败'
      if (nowcoderVerificationRequired(error.payload) || message.includes('验证') || message.includes('安全') || message.includes('风控')) {
        await requestNowcoderVerification(task, message)
      } else if (message.includes('登录') || message.toLowerCase().includes('token')) {
        publishBridgeEvent(task, 'AUTH_REQUIRED', { message })
        if (!window.location.pathname.startsWith('/login')) {
          const callback = new URL(task.target_url)
          callback.hash = ''
          window.location.assign(`/login?callBack=${encodeURIComponent(callback.toString())}`)
        }
      } else {
        publishBridgeEvent(task, 'FAILED', { message })
        discardTask(task)
      }
    }
  }

  function luoguPageContext (root = document) {
    const node = root.getElementById('lentille-context')
    if (!node) return null
    try {
      return JSON.parse(node.textContent || '{}')
    } catch (error) {
      return null
    }
  }

  function luoguChallengeVisible (root = document, html = '') {
    const title = String(root.title || '').toLowerCase()
    const source = String(html || '').toLowerCase()
    return !luoguPageContext(root) && (
      title.includes('just a moment') ||
      Boolean(root.querySelector('iframe[src*="challenges.cloudflare.com"], [id^="challenge-"], #challenge-form')) ||
      source.includes('challenges.cloudflare.com') || source.includes('cf-chl-')
    )
  }

  function luoguChallengeResponse (response) {
    if (!response) return false
    const html = String(response.responseText || '')
    if (!html) return false
    const root = new DOMParser().parseFromString(html, 'text/html')
    return luoguChallengeVisible(root, html)
  }

  function luoguCaptchaRequired (payload) {
    const nested = payload && payload.data && typeof payload.data === 'object'
      ? payload.data
      : {}
    const errorType = String((payload && payload.errorType) || nested.errorType || '')
    const errorData = (payload && payload.errorData) || nested.errorData || {}
    const message = String(
      (payload && (payload.message || payload.errorMessage)) ||
      nested.message || nested.errorMessage || ''
    )
    return errorType.endsWith('CaptchaNotMatchException') ||
      errorType.endsWith('InvalidCaptchaException') ||
      /captcha|turnstile|verification/i.test(errorType) ||
      Boolean(errorData.interactive || errorData.turnstile || errorData.captcha) ||
      /验证码|人机验证|captcha|turnstile/i.test(message)
  }

  function luoguAuthRequired (payload) {
    const nested = payload && payload.data && typeof payload.data === 'object'
      ? payload.data
      : {}
    const text = (
      `${(payload && payload.errorType) || nested.errorType || ''} ` +
      `${(payload && (payload.message || payload.errorMessage)) || nested.message || nested.errorMessage || ''}`
    ).toLowerCase()
    return text.includes('unauthorized') || text.includes('authentication') || text.includes('login') ||
      text.includes('未登录') || text.includes('登录')
  }

  function luoguSubmissionId (payload) {
    if (!payload || luoguCaptchaRequired(payload) || luoguAuthRequired(payload)) return ''
    const body = (payload && payload.data) || payload || {}
    if (payload.errorType || body.errorType || payload.error || body.error ||
        payload.success === false || body.success === false) return ''
    return body.rid || body.recordId || body.id || ''
  }

  const LUOGU_STATUS = {
    2: 'COMPILE_ERROR',
    3: 'OUTPUT_LIMIT_EXCEEDED',
    4: 'MEMORY_LIMIT_EXCEEDED',
    5: 'TIME_LIMIT_EXCEEDED',
    6: 'WRONG_ANSWER',
    7: 'RUNTIME_ERROR',
    8: 'SYSTEM_ERROR',
    11: 'SYSTEM_ERROR',
    12: 'ACCEPTED',
    13: 'PARTIALLY_ACCEPTED',
    14: 'PARTIALLY_ACCEPTED',
    21: 'ACCEPTED'
  }

  const LUOGU_VERDICT_ALIASES = {
    OK: 'ACCEPTED',
    AC: 'ACCEPTED',
    ACCEPTED: 'ACCEPTED',
    COMPILE_ERROR: 'COMPILE_ERROR',
    COMPILATION_ERROR: 'COMPILE_ERROR',
    CE: 'COMPILE_ERROR',
    OUTPUT_LIMIT_EXCEEDED: 'OUTPUT_LIMIT_EXCEEDED',
    OLE: 'OUTPUT_LIMIT_EXCEEDED',
    MEMORY_LIMIT_EXCEEDED: 'MEMORY_LIMIT_EXCEEDED',
    MLE: 'MEMORY_LIMIT_EXCEEDED',
    TIME_LIMIT_EXCEEDED: 'TIME_LIMIT_EXCEEDED',
    TLE: 'TIME_LIMIT_EXCEEDED',
    WRONG_ANSWER: 'WRONG_ANSWER',
    WA: 'WRONG_ANSWER',
    RUNTIME_ERROR: 'RUNTIME_ERROR',
    RE: 'RUNTIME_ERROR',
    SYSTEM_ERROR: 'SYSTEM_ERROR',
    UNKNOWN_ERROR: 'SYSTEM_ERROR',
    JUDGEMENT_FAILED: 'SYSTEM_ERROR',
    JUDGE_FAILED: 'SYSTEM_ERROR',
    SE: 'SYSTEM_ERROR',
    PARTIALLY_ACCEPTED: 'PARTIALLY_ACCEPTED',
    PARTIAL_ACCEPTED: 'PARTIALLY_ACCEPTED',
    PARTIAL: 'PARTIALLY_ACCEPTED',
    UNACCEPTED: 'PARTIALLY_ACCEPTED'
  }

  const LUOGU_CASE_STATUS = {
    4: 'ACCEPTED',
    5: 'WRONG_ANSWER',
    6: 'WRONG_ANSWER',
    7: 'TIME_LIMIT_EXCEEDED',
    8: 'MEMORY_LIMIT_EXCEEDED',
    9: 'RUNTIME_ERROR',
    10: 'COMPILE_ERROR',
    11: 'OUTPUT_LIMIT_EXCEEDED',
    12: 'ACCEPTED',
    13: 'SYSTEM_ERROR',
    14: 'WRONG_ANSWER'
  }

  function acceptLuoguSubmission (task, submissionId) {
    const id = String(submissionId || '')
    if (!id) throw new Error('洛谷没有返回评测记录 ID')
    if (task.remote_submission_id || task.terminal_event) return
    task.remote_submission_id = id
    task.adapter_state = { phase: 'JUDGING', submission_id: id }
    delete task.code
    saveTask(task)
    const remoteUrl = `https://www.luogu.com.cn/record/${id}`
    publishBridgeEvent(task, 'SUBMITTED', {
      remote_submission_id: id,
      remote_url: remoteUrl,
      message: '洛谷已接收提交'
    })
    publishBridgeEvent(task, 'JUDGING', {
      remote_submission_id: id,
      remote_url: remoteUrl,
      message: '洛谷正在判题'
    })
    handOffJudgingToOj()
  }

  function luoguLooksLikeRecord (value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false
    const identityKeys = ['rid', 'recordId', 'pid', 'problem', 'problemId']
    const resultKeys = [
      'judgeStatus', 'statusCode', 'statusText', 'statusName', 'verdict',
      'score', 'time', 'timeCost', 'memory', 'memoryCost', 'judgeResult'
    ]
    return identityKeys.some(key => value[key] !== undefined) ||
      resultKeys.some(key => value[key] !== undefined) ||
      (value.id !== undefined && value.status !== undefined)
  }

  function luoguRecordData (payload) {
    const roots = [payload && payload.currentData, payload && payload.data]
    const containerKeys = ['record', 'submission', 'recordData', 'judgeRecord', 'detail']
    for (const root of roots) {
      if (!root || typeof root !== 'object' || Array.isArray(root)) continue
      if (luoguLooksLikeRecord(root)) return root
      for (const key of containerKeys) {
        if (root[key] && typeof root[key] === 'object' && !Array.isArray(root[key])) return root[key]
      }
      for (const key of ['result', 'data']) {
        const nested = root[key]
        if (!nested || typeof nested !== 'object' || Array.isArray(nested)) continue
        for (const containerKey of containerKeys) {
          if (nested[containerKey] && typeof nested[containerKey] === 'object' &&
            !Array.isArray(nested[containerKey])) return nested[containerKey]
        }
        if (luoguLooksLikeRecord(nested)) return nested
      }
    }
    return {}
  }

  function luoguScalar (value) {
    return value !== null && value !== undefined && typeof value !== 'object'
      ? String(value).trim()
      : ''
  }

  function luoguValues (value) {
    if (Array.isArray(value)) return value
    if (value && typeof value === 'object') return Object.values(value)
    return []
  }

  function luoguDerivedVerdict (record) {
    const detail = record && record.detail && typeof record.detail === 'object'
      ? record.detail
      : {}
    const compileResult = detail.compileResult || record.compileResult
    const judgeResult = detail.judgeResult || record.judgeResult
    if (compileResult && typeof compileResult === 'object') {
      if (compileResult.success === false) return 'COMPILE_ERROR'
    }
    if (!judgeResult || typeof judgeResult !== 'object') return ''

    const testCases = []
    for (const subtask of luoguValues(judgeResult.subtasks)) {
      if (!subtask || typeof subtask !== 'object') continue
      testCases.push(...luoguValues(subtask.testCases || subtask.cases))
    }
    if (!testCases.length) {
      return Number(record.score) >= 100 ? 'ACCEPTED' : ''
    }

    const codes = testCases
      .map(testCase => Number(testCase && testCase.status))
      .filter(Number.isFinite)
    if (!codes.length || codes.some(code => code >= 0 && code <= 3)) return ''
    if (codes.every(code => code === 4 || code === 12)) return 'ACCEPTED'
    const failedCode = codes.find(code => code !== 4 && code !== 12)
    return LUOGU_CASE_STATUS[failedCode] || 'WRONG_ANSWER'
  }

  function luoguStatusDetails (record) {
    const statusObjects = [record.status, record.judgeStatus, record.judgeResult, record.result]
      .filter(value => value && typeof value === 'object' && !Array.isArray(value))
    const codeValues = [record.statusCode, record.judgeStatus, record.status]
    for (const statusObject of statusObjects) {
      codeValues.push(
        statusObject.statusCode,
        statusObject.code,
        statusObject.id,
        statusObject.value,
        statusObject.status
      )
    }
    let code = null
    for (const value of codeValues) {
      const scalar = luoguScalar(value)
      if (!/^-?\d+$/.test(scalar)) continue
      code = Number(scalar)
      break
    }

    const textValues = [
      record.statusText,
      record.statusName,
      record.verdict,
      luoguScalar(record.result),
      luoguScalar(record.judgeStatus),
      luoguScalar(record.status)
    ]
    for (const statusObject of statusObjects) {
      textValues.push(
        statusObject.displayName,
        statusObject.name,
        statusObject.text,
        statusObject.label,
        statusObject.verdict
      )
    }
    const text = textValues.map(luoguScalar).find(value => value && !/^-?\d+$/.test(value)) || ''
    const normalized = text.toUpperCase().replace(/[\s-]+/g, '_')
    // The overall record status is authoritative. Compiler output may contain
    // warnings or success messages while judging is still in progress.
    const pending = code === 0 || code === 1 ||
      (code === null && /WAIT|JUDGING|PENDING|QUEUE|COMPILING|RUNNING|评测中|判题中|等待|编译中|运行中/i.test(text))
    if (pending) return { code, text, pending: true, verdict: '' }
    const verdict = LUOGU_STATUS[code] || LUOGU_VERDICT_ALIASES[normalized] ||
      (/部分正确|未通过/.test(text) ? 'PARTIALLY_ACCEPTED' : '') ||
      (/答案正确|通过/.test(text) ? 'ACCEPTED' : '') ||
      (/编译错误/.test(text) ? 'COMPILE_ERROR' : '') ||
      (/输出超限/.test(text) ? 'OUTPUT_LIMIT_EXCEEDED' : '') ||
      (/内存超限/.test(text) ? 'MEMORY_LIMIT_EXCEEDED' : '') ||
      (/时间超限|运行超时|超时/.test(text) ? 'TIME_LIMIT_EXCEEDED' : '') ||
      (/答案错误/.test(text) ? 'WRONG_ANSWER' : '') ||
      (/运行错误/.test(text) ? 'RUNTIME_ERROR' : '') ||
      (/系统错误|评测失败|未知错误/.test(text) ? 'SYSTEM_ERROR' : '') ||
      luoguDerivedVerdict(record)
    return { code, text, pending: false, verdict }
  }

  function luoguLoginTemplate (payload) {
    const template = String((payload && (payload.currentTemplate || payload.template)) || '').toLowerCase()
    return template.includes('login') || template.includes('auth')
  }

  async function pollLuoguRecord (task) {
    const submissionId = String((task.adapter_state || {}).submission_id || task.remote_submission_id || '')
    if (!submissionId) return
    const deadline = Date.now() + 180000
    while (Date.now() < deadline && pollingActive(task)) {
      try {
        const payload = await gmJsonRequest(
          'GET',
          `https://www.luogu.com.cn/record/${encodeURIComponent(submissionId)}?_contentOnly=1`,
          null,
          {'x-lentille-request': 'content-only'}
        )
        if (luoguLoginTemplate(payload) || luoguAuthRequired(payload)) {
          const message = '洛谷登录状态已失效'
          if (window.location.origin === OJ_ORIGIN) openProviderActionTab(task, 'AUTH_REQUIRED', message)
          else publishBridgeEvent(task, 'AUTH_REQUIRED', { message })
          return
        }
        const record = luoguRecordData(payload)
        const status = luoguStatusDetails(record)
        if (status.pending || !status.verdict) {
          await sleep(1500)
          continue
        }
        const compileResult = (record.detail || {}).compileResult || record.compileResult || {}
        const compileMessage = status.verdict === 'COMPILE_ERROR'
          ? String(compileResult.message || '').trim().slice(0, 2048)
          : ''
        const failure = luoguDerivedVerdict(record)
        const isUnaccepted = status.verdict === 'PARTIALLY_ACCEPTED'
        const verdict = isUnaccepted && (task.rule_type === 'ACM' || Number(record.score) === 0)
          ? (failure && failure !== 'ACCEPTED' ? failure : 'WRONG_ANSWER') : status.verdict
        publishBridgeEvent(task, 'FINISHED', {
          remote_submission_id: submissionId,
          remote_url: `https://www.luogu.com.cn/record/${submissionId}`,
          verdict,
          failed_verdict: failure !== 'ACCEPTED' ? failure : '',
          time_ms: Number(record.time || record.timeCost || 0),
          memory_bytes: Number(record.memory || record.memoryCost || 0) * 1024,
          score: record.score,
          message: compileMessage || status.text || status.verdict,
          verification_source: 'luogu-session-page'
        })
        returnToOj(task)
        return
      } catch (error) {
        const response = error && error.response
        const finalUrl = String((response && response.finalUrl) || '')
        if (luoguAuthRequired(error.payload) || error.status === 401 || finalUrl.includes('/auth/login')) {
          const message = error.message || '洛谷登录状态已失效'
          if (window.location.origin === OJ_ORIGIN) openProviderActionTab(task, 'AUTH_REQUIRED', message)
          else publishBridgeEvent(task, 'AUTH_REQUIRED', { message })
          return
        }
        if (luoguChallengeResponse(response) ||
            (response && (response.status === 403 || (response.status >= 200 && response.status < 300)))) {
          const message = '洛谷要求在浏览器页面完成安全验证'
          if (window.location.origin === OJ_ORIGIN) {
            openProviderActionTab(task, 'VERIFICATION_REQUIRED', message, {
              verification_source: 'luogu-session-page'
            })
          } else {
            publishBridgeEvent(task, 'VERIFICATION_REQUIRED', {
              message,
              verification_source: 'luogu-session-page'
            })
          }
          return
        }
      }
      await sleep(1500)
    }
    if (!pollingActive(task)) return
    publishBridgeEvent(task, 'JUDGING', {
      remote_submission_id: submissionId,
      remote_url: `https://www.luogu.com.cn/record/${submissionId}`,
      message: '洛谷判题时间较长，请保留此标签页或稍后查看评测记录'
    })
  }

  function installLuoguXhrInterceptor (task) {
    const Xhr = unsafeWindow.XMLHttpRequest
    if (!Xhr) return
    unsafeWindow.__xjuOjRemoteBridgeLuoguTask = task
    if (Xhr.prototype.__xjuOjRemoteBridgePatched) return
    Xhr.prototype.__xjuOjRemoteBridgePatched = true
    const originalOpen = Xhr.prototype.open
    const originalSend = Xhr.prototype.send
    Xhr.prototype.open = function (method, url, ...rest) {
      this.__xjuOjRemoteUrl = String(url || '')
      return originalOpen.call(this, method, url, ...rest)
    }
    Xhr.prototype.send = function (body) {
      let requestPath = ''
      try {
        requestPath = new URL(this.__xjuOjRemoteUrl, window.location.origin).pathname
      } catch (error) {}
      const activeTask = nativeSubmissionTask('LUOGU', requestPath)
      let outgoingBody = body
      if (activeTask && /^\/fe\/api\/problem\/submit\//.test(requestPath)) {
        try {
          const payload = typeof body === 'string' ? JSON.parse(body) : body
          if (payload && typeof payload === 'object' && !(payload instanceof FormData)) {
            payload.lang = Number(activeTask.language_id)
            payload.code = activeTask.code
            payload.enableO2 = 0
            outgoingBody = typeof body === 'string' ? JSON.stringify(payload) : payload
          }
        } catch (error) {}
        this.addEventListener('load', () => {
          try {
            const responsePayload = JSON.parse(this.responseText || '{}')
            const submissionId = luoguSubmissionId(responsePayload)
            if (submissionId) acceptLuoguSubmission(activeTask, submissionId)
          } catch (error) {}
        }, { once: true })
      }
      return originalSend.call(this, outgoingBody)
    }

    const originalFetch = unsafeWindow.fetch
    if (originalFetch && !originalFetch.__xjuOjRemoteBridgeLuoguPatched) {
      const patchedFetch = async function (input, init = {}) {
        let requestPath = ''
        try {
          requestPath = new URL(typeof input === 'string' ? input : input.url, window.location.origin).pathname
        } catch (error) {}
        let outgoingInit = init
        const activeTask = nativeSubmissionTask('LUOGU', requestPath)
        if (/^\/fe\/api\/problem\/submit\//.test(requestPath)) {
          try {
            const payload = typeof init.body === 'string' ? JSON.parse(init.body) : init.body
            if (activeTask && payload && typeof payload === 'object' && !(payload instanceof FormData)) {
              payload.lang = Number(activeTask.language_id)
              payload.code = activeTask.code
              payload.enableO2 = 0
              outgoingInit = { ...init, body: typeof init.body === 'string' ? JSON.stringify(payload) : payload }
            }
          } catch (error) {}
        }
        const response = await originalFetch.call(this, input, outgoingInit)
        if (/^\/fe\/api\/problem\/submit\//.test(requestPath)) {
          response.clone().json().then(payload => {
            const submissionId = luoguSubmissionId(payload)
            if (activeTask && submissionId) acceptLuoguSubmission(activeTask, submissionId)
          }).catch(() => {})
        }
        return response
      }
      patchedFetch.__xjuOjRemoteBridgeLuoguPatched = true
      unsafeWindow.fetch = patchedFetch
    }
  }

  async function prepareLuoguNativeVerification (task) {
    installLuoguXhrInterceptor(task)
    publishBridgeEvent(task, 'VERIFICATION_REQUIRED', {
      message: '请在洛谷当前标签页完成官方人机验证；成功后将自动回到 OJ'
    })
    if (window.location.hash !== '#submit') window.location.hash = 'submit'

    const deadline = Date.now() + 20000
    while (Date.now() < deadline) {
      const submitter = Array.from(document.querySelectorAll('button')).find(button => {
        const label = String(button.textContent || '').trim()
        return label.includes('提交评测') || label === 'Submit to Judge'
      })
      if (submitter) {
        submitter.click()
        return
      }
      await sleep(300)
    }
    throw new Error('洛谷提交面板没有及时加载，请刷新当前标签页后重试')
  }

  async function requestLuoguVerification (task, message, verificationSource = 'luogu-submit') {
    if (!task.remote_submission_id) { task.adapter_state = { phase: 'NEEDS_ACTION' }; saveTask(task) }
    if (window.location.origin === OJ_ORIGIN) {
      openProviderActionTab(
        task,
        'VERIFICATION_REQUIRED',
        message || '请在洛谷原生页面完成人机验证',
        { verification_source: verificationSource }
      )
      return
    }
    await prepareLuoguNativeVerification(task)
  }

  async function submitLuoguDirect (task) {
    const problemId = String((task.provider_data || {}).problem_id || task.problem_id || '')
    if (!problemId) throw new Error('洛谷题目缺少 problemId')
    const referer = task.target_url.split('#')[0]
    let root = document
    if (window.location.origin === OJ_ORIGIN) {
      const pageResponse = await gmRawRequest('GET', referer, null, {
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
      })
      const html = pageResponse.responseText || ''
      root = new DOMParser().parseFromString(html, 'text/html')
      if (luoguChallengeVisible(root, html)) {
        await requestLuoguVerification(task, '请在洛谷页面完成浏览器安全验证', 'luogu-cloudflare')
        return false
      }
      const finalUrl = new URL(pageResponse.finalUrl || referer)
      const context = luoguPageContext(root)
      if (finalUrl.pathname.startsWith('/auth/login') || !context || !context.user) {
        openProviderActionTab(task, 'AUTH_REQUIRED', '洛谷登录状态已失效，请重新登录')
        return false
      }
      if (pageResponse.status < 200 || pageResponse.status >= 300) {
        throw new Error(`洛谷题目页返回 HTTP ${pageResponse.status}`)
      }
    }

    const csrf = root.querySelector('meta[name="csrf-token"]')
    if (!csrf || !csrf.getAttribute('content')) throw new Error('洛谷题目页缺少 CSRF 信息')
    const response = await sendProviderCode(task, () => gmRawRequest(
      'POST',
      `https://www.luogu.com.cn/fe/api/problem/submit/${encodeURIComponent(problemId)}`,
      JSON.stringify({
        lang: Number(task.language_id),
        code: task.code,
        enableO2: 0
      }),
      {
        Accept: 'application/json, text/plain, */*',
        'Content-Type': 'application/json;charset=UTF-8',
        'X-CSRF-TOKEN': csrf.getAttribute('content') || '',
        'X-Requested-With': 'XMLHttpRequest',
        Origin: 'https://www.luogu.com.cn',
        Referer: referer
      }
    ))
    let payload
    try {
      payload = responseJson(response)
    } catch (error) {
      throw new Error(`洛谷提交接口返回 HTTP ${response.status}`)
    }
    if (luoguCaptchaRequired(payload)) {
      await requestLuoguVerification(task, payload.message || '洛谷要求完成人机验证')
      return false
    }
    if (luoguAuthRequired(payload) || response.status === 401 || response.status === 403) {
      if (window.location.origin === OJ_ORIGIN) {
        openProviderActionTab(task, 'AUTH_REQUIRED', '洛谷登录状态已失效，请重新登录')
        return false
      }
      throw new Error('洛谷账号尚未登录或登录状态已失效')
    }
    const submissionId = luoguSubmissionId(payload)
    if (submissionId) {
      acceptLuoguSubmission(task, submissionId)
      return true
    }
    throw new Error(payload.message || payload.errorMessage || `洛谷提交失败，HTTP ${response.status}`)
  }

  async function bootLuoguTask (task) {
    if (luoguChallengeVisible()) {
      publishBridgeEvent(task, 'VERIFICATION_REQUIRED', {
        message: '请在当前标签页完成洛谷的浏览器安全验证'
      })
      return
    }

    const state = task.adapter_state || {}
    if (state.phase === 'JUDGING' && state.submission_id) {
      await restoreRemoteQuery(task)
      return
    }

    const context = luoguPageContext()
    if (!context || !context.user) {
      publishBridgeEvent(task, 'AUTH_REQUIRED', {
        message: '请先登录洛谷，登录成功后脚本会返回题目并继续提交'
      })
      if (!window.location.pathname.startsWith('/auth/login')) window.location.assign('/auth/login')
      return
    }

    const problemId = String((task.provider_data || {}).problem_id || task.problem_id || '')
    if (!window.location.pathname.includes(`/problem/${problemId}`)) {
      window.location.replace(task.target_url)
      return
    }

    try {
      publishBridgeEvent(task, 'OPENING', { message: '正在通过洛谷网页会话提交代码' })
      await submitLuoguDirect(task)
    } catch (error) {
      if (error.submitUncertain) return
      const message = error.message || '洛谷提交失败'
      if (message.includes('登录')) {
        publishBridgeEvent(task, 'AUTH_REQUIRED', { message })
        if (!window.location.pathname.startsWith('/auth/login')) window.location.assign('/auth/login')
      } else {
        publishBridgeEvent(task, 'FAILED', { message })
        discardTask(task)
      }
    }
  }

  async function sendProviderCode (task, send) {
    const lease = await acquireLease(task.submission_id, 'submit')
    const stored = GM_getValue(taskStorageKey(task.submission_id), null)
    if (!lease || (stored && (stored.remote_submission_id || stored.terminal_event ||
        ['SUBMITTING', 'SUBMIT_UNCERTAIN'].includes((stored.adapter_state || {}).phase)))) {
      if (lease) lease.release()
      const error = new Error('这条提交已在处理中，请先核对远端记录')
      error.submitUncertain = true
      throw error
    }
    task.adapter_state = { phase: 'SUBMITTING', started_at: Date.now() }
    saveTask(task)
    try {
      const response = await send()
      if (response && response.status >= 500) {
        const error = new Error('远端服务暂时不可用，提交状态待确认')
        error.status = response.status
        throw error
      }
      // Keep an uncertain marker until the caller records an ID or an explicit
      // verification/rejection response, including across a tab closing here.
      task.adapter_state.phase = 'SUBMIT_UNCERTAIN'
      saveTask(task)
      return response
    } catch (error) {
      if (isRemoteConnectionError(error) || error.status >= 500 ||
          (error.response && error.response.status >= 200 && error.response.status < 300)) {
        task.adapter_state.phase = 'SUBMIT_UNCERTAIN'
        error.submitUncertain = true
        publishBridgeEvent(task, 'OPENING', {
          message: '提交时连接中断，远端可能已经接收代码。任务已保留，请先在原站核对记录，避免重复提交'
        })
      } else {
        task.adapter_state = {}
        saveTask(task)
      }
      throw error
    } finally { lease.release() }
  }

  function pollingActive (task) {
    if (window.location.origin === OJ_ORIGIN && String(task.user_id) !== String(currentOjUserId)) return false
    const stored = GM_getValue(taskStorageKey(task.submission_id), null)
    if (!stored || stored.terminal_event) return false
    const lease = activePollLeases.get(task.submission_id)
    return !lease || lease.renew()
  }

  function schedulePoll (task, delay = 5000) {
    if (pollTimers.has(task.submission_id)) return
    pollTimers.set(task.submission_id, window.setTimeout(() => {
      pollTimers.delete(task.submission_id)
      const stored = GM_getValue(taskStorageKey(task.submission_id), null)
      if (stored) resumeOjJudgingTask(stored)
    }, delay))
  }

  async function refreshNowcoderQueryState (task) {
    const referer = task.target_url.split('#')[0]
    const account = await nowcoderAccountContext(referer)
    const previous = task.adapter_state || {}
    if (previous.user_id && Number(previous.user_id) !== account.user_id) {
      throw new Error('请登录原牛客账号以查询这条提交')
    }
    const token = await nowcoderAccessToken(referer)
    task.adapter_state = {
      ...previous, phase: 'JUDGING', submission_id: String(task.remote_submission_id || previous.submission_id),
      user_id: account.user_id, app_id: account.app_id,
      tag_id: Number((task.provider_data || {}).tag_id || previous.tag_id || 0), referer, token
    }
    saveTask(task)
  }

  function resumeOjJudgingTask (task) {
    if (!task || ojPollingSubmissions.has(task.submission_id)) return Promise.resolve()
    if (task.terminal_event) { postBridgeEvent(task.terminal_event); return Promise.resolve() }
    if (window.location.origin === OJ_ORIGIN && (!currentOjUserId ||
        String(task.user_id) !== String(currentOjUserId))) return Promise.resolve()
    if (ACTION_STATUSES.has(task.status)) return Promise.resolve()
    if ((task.adapter_state || {}).phase !== 'JUDGING' &&
        (task.adapter_state || {}).phase !== 'AWAITING_ID') return Promise.resolve()
    if (ojPollingSubmissions.size >= 3) { schedulePoll(task, 10000); return Promise.resolve() }
    ojPollingSubmissions.add(task.submission_id)
    let lease
    return Promise.resolve().then(async () => {
      lease = await acquireLease(task.submission_id, 'poll')
      if (!lease || !pollingActive(task)) return
      activePollLeases.set(task.submission_id, lease)
      if (task.provider === 'NOWCODER') {
        if (!(task.adapter_state || {}).token) await refreshNowcoderQueryState(task)
        await pollNowcoderRun(task)
      } else if (task.provider === 'LUOGU') await pollLuoguRecord(task)
      else if (task.provider === 'CODEFORCES') {
        if (!(task.adapter_state || {}).handle) {
          const page = await gmRawRequest('GET', task.target_url.split('#')[0])
          const root = new DOMParser().parseFromString(page.responseText || '', 'text/html')
          if (codeforcesChallengeVisible(root, page.responseText || '')) {
            openProviderActionTab(task, 'VERIFICATION_REQUIRED', '请在 Codeforces 页面完成验证后继续查询结果')
            return
          }
          const handle = codeforcesHandle(root)
          if (!handle) throw new Error('请登录原 Codeforces 账号以查询提交')
          task.adapter_state.handle = handle
          saveTask(task)
        }
        await pollCodeforcesRun(task)
      }
    }).catch(error => {
      const message = error.message || '暂时无法查询远程结果，将自动重试'
      if (message.includes('登录') || message.toLowerCase().includes('token')) {
        publishBridgeEvent(task, 'AUTH_REQUIRED', { message })
      } else if (task.remote_submission_id) {
        publishBridgeEvent(task, 'JUDGING', { remote_submission_id: task.remote_submission_id, message })
      }
    }).finally(() => {
      if (lease) lease.release()
      activePollLeases.delete(task.submission_id)
      ojPollingSubmissions.delete(task.submission_id)
      const stored = GM_getValue(taskStorageKey(task.submission_id), null)
      if (stored && !stored.terminal_event && !ACTION_STATUSES.has(stored.status)) schedulePoll(stored)
    })
  }

  async function restoreRemoteQuery (task) {
    task.status = 'JUDGING'
    task.adapter_state = { ...(task.adapter_state || {}), phase: 'JUDGING', submission_id: String(task.remote_submission_id) }
    saveTask(task)
    await resumeOjJudgingTask(task)
  }

  async function recoverOjTasks () {
    if (recovering || window.location.origin !== OJ_ORIGIN) return
    recovering = true
    try {
      const data = await ojRequest('/api/remote_submission/recover')
      if (!data || !data.user_id || !Array.isArray(data.tasks)) return
      if (String(currentOjUserId) !== String(data.user_id)) ownedSubmissionIds.clear()
      currentOjUserId = data.user_id
      for (const fresh of data.tasks) {
        ownedSubmissionIds.add(fresh.submission_id)
        const previous = GM_getValue(taskStorageKey(fresh.submission_id), {}) || {}
        const task = { ...previous, ...fresh }
        saveTask(task)
        if (task.terminal_event) postBridgeEvent(task.terminal_event)
        else if (!ACTION_STATUSES.has(task.remote_status)) restoreRemoteQuery(task).catch(() => {})
      }
      const keys = typeof GM_listValues === 'function' ? GM_listValues() : []
      for (const key of keys.filter(key => key.startsWith(`${STORAGE_PREFIX}:task:`))) {
        const task = GM_getValue(key, null)
        if (!task || String(task.user_id) !== String(currentOjUserId)) continue
        ownedSubmissionIds.add(task.submission_id)
        if (task.terminal_event) postBridgeEvent(task.terminal_event)
        else resumeOjJudgingTask(task)
      }
      for (const key of keys.filter(key => key.startsWith(`${STORAGE_PREFIX}:outbox:`))) {
        const event = GM_getValue(key, null)
        if (event) flushOutbox(event.submission_id)
      }
    } catch (_) {
      // Login and connectivity can recover later; persistent results stay put.
    } finally {
      recovering = false
      window.clearTimeout(recoveryTimer)
      recoveryTimer = window.setTimeout(recoverOjTasks, 60000)
    }
  }

  async function runRemoteTaskFromOj (task) {
    publishBridgeEvent(task, 'OPENING', { message: `正在后台连接 ${task.provider}` })
    if (task.provider === 'CODEFORCES') {
      await submitCodeforcesFromOj(task)
      return
    }
    if (task.provider === 'NOWCODER') {
      try {
        const accepted = await submitNowcoderDirect(task)
        if (accepted) await resumeOjJudgingTask(task)
      } catch (error) {
        const message = error.message || '牛客提交失败'
        if (nowcoderVerificationRequired(error.payload) || message.includes('验证') || message.includes('安全') || message.includes('风控')) {
          await requestNowcoderVerification(task, message)
        } else if (nowcoderAuthRequired(error.payload) || message.includes('登录') || message.toLowerCase().includes('token')) {
          openProviderActionTab(task, 'AUTH_REQUIRED', message)
        } else {
          throw error
        }
      }
      return
    }
    if (task.provider === 'LUOGU') {
      const accepted = await submitLuoguDirect(task)
      if (accepted) await resumeOjJudgingTask(task)
      return
    }
    throw new Error(`不支持的远程平台：${task.provider}`)
  }

  async function startRemoteTask (event) {
    const id = event && event.detail && event.detail.task && event.detail.task.submission_id
    if (!id || startingSubmissions.has(id)) return
    startingSubmissions.add(id)
    try {
      await startRemoteTaskOnce(event)
    } finally { startingSubmissions.delete(id) }
  }

  async function startRemoteTaskOnce (event) {
    let task
    try {
      task = normalizeTask(event && event.detail)
      currentOjUserId = task.user_id || currentOjUserId
      ownedSubmissionIds.add(task.submission_id)
      const previous = GM_getValue(taskStorageKey(task.submission_id), null)
      if (previous && previous.terminal_event) { postBridgeEvent(previous.terminal_event); return }
      if ((previous && previous.remote_submission_id) || task.remote_submission_id) {
        task = { ...(previous || {}), ...task,
          remote_submission_id: task.remote_submission_id || previous.remote_submission_id,
          adapter_state: (previous || {}).adapter_state }
        await restoreRemoteQuery(task)
        return
      }
      if (previous && (previous.adapter_state || {}).phase === 'AWAITING_ID') {
        await resumeOjJudgingTask(previous)
        return
      }
      if (previous && ['SUBMITTING', 'SUBMIT_UNCERTAIN'].includes((previous.adapter_state || {}).phase)) {
        publishBridgeEvent(previous, 'OPENING', { message: '这条提交可能已被远端接收，请先在原站核对记录，避免重复提交代码' })
        return
      }
      GM_setValue(taskStorageKey(task.submission_id), task)
      GM_setValue(activeTaskStorageKey(task.provider), task.submission_id)
      publishBridgeEvent(task, task.remote_status && task.remote_status !== 'QUEUED' ? 'OPENING' : 'QUEUED', {
        message: '远程提交任务已交给浏览器脚本'
      })
    } catch (error) {
      const rawTask = event && event.detail && event.detail.task
      if (rawTask && rawTask.submission_id && rawTask.provider) {
        publishBridgeEvent(rawTask, 'FAILED', { message: error.message || '远程提交任务无效' })
      }
      return
    }
    try {
      await runRemoteTaskFromOj(task)
    } catch (error) {
      if (error.submitUncertain) return
      const response = error && error.response
      if (task.provider === 'CODEFORCES' && response) {
        const html = response.responseText || ''
        const root = new DOMParser().parseFromString(html, 'text/html')
        if (codeforcesVerificationVisible(root, html)) {
          openProviderActionTab(
            task,
            'VERIFICATION_REQUIRED',
            '请在 Codeforces 页面完成人机验证',
            { verification_source: 'codeforces-cloudflare' }
          )
          return
        }
      }
      if (task.provider === 'CODEFORCES' && isRemoteConnectionError(error)) {
        openProviderRetryTab(
          task,
          '暂时无法后台连接 Codeforces，已切换到原生页面继续提交'
        )
        return
      }
      publishBridgeEvent(task, 'FAILED', { message: error.message || '远程提交失败' })
      discardTask(task)
    }
  }

  function startRemoteImport (event) {
    let task
    try {
      task = normalizeImportTask(event && event.detail)
      GM_setValue(importTaskStorageKey(task.request_id), task)
      GM_setValue(activeImportStorageKey(task.provider), task.request_id)
      publishImportEvent(task, 'OPENING', { message: '正在打开 Codeforces 题面' })
      GM_openInTab(task.target_url, { active: true, insert: true, setParent: true })
    } catch (error) {
      const detail = event && event.detail
      if (detail && detail.request_id) {
        publishImportEvent(detail, 'FAILED', { message: error.message || '远程导题任务无效' })
      }
    }
  }

  function bootOjBridge () {
    const resumeStoredTask = task => {
      if (!task || task.schema !== TASK_SCHEMA) return
      const phase = (task.adapter_state || {}).phase
      const shouldResume = phase === 'JUDGING' ||
        (task.provider === 'CODEFORCES' && phase === 'AWAITING_ID')
      if (shouldResume) resumeOjJudgingTask(task)
    }
    const resumeJudging = event => {
      if (!event) return
      const task = GM_getValue(taskStorageKey(event.submission_id), null)
      if (!task || task.schema !== TASK_SCHEMA) return
      const phase = (task.adapter_state || {}).phase
      const shouldResume = event.status === 'JUDGING' && phase === 'JUDGING'
      const codeforcesAwaitingId = task.provider === 'CODEFORCES' && event.status === 'OPENING' && phase === 'AWAITING_ID'
      if (!shouldResume && !codeforcesAwaitingId) return
      resumeOjJudgingTask(task)
    }
    window.addEventListener(SUBMIT_EVENT, startRemoteTask)
    window.addEventListener('online', recoverOjTasks)
    window.addEventListener('focus', recoverOjTasks)
    recoverOjTasks()
    window.addEventListener(IMPORT_EVENT, startRemoteImport)
    GM_addValueChangeListener(EVENT_STORAGE_KEY, (_name, _oldValue, newValue) => {
      dispatchBridgeEvent(newValue)
      resumeJudging(newValue)
    })
    const latestEvent = GM_getValue(EVENT_STORAGE_KEY, null)
    if (latestEvent) window.setTimeout(() => {
      dispatchBridgeEvent(latestEvent)
      resumeJudging(latestEvent)
    }, 0)
    window.setTimeout(() => {
      const taskKeyPrefix = `${STORAGE_PREFIX}:task:`
      const storedTaskKeys = typeof GM_listValues === 'function'
        ? GM_listValues().filter(key => key.startsWith(taskKeyPrefix))
        : []
      if (storedTaskKeys.length) {
        for (const key of storedTaskKeys) resumeStoredTask(GM_getValue(key, null))
        return
      }
      for (const provider of ['CODEFORCES', 'NOWCODER', 'LUOGU']) {
        const submissionId = GM_getValue(activeTaskStorageKey(provider), '')
        if (submissionId) resumeStoredTask(GM_getValue(taskStorageKey(submissionId), null))
      }
    }, 0)
    GM_addValueChangeListener(IMPORT_EVENT_STORAGE_KEY, (_name, _oldValue, newValue) => {
      dispatchImportEvent(newValue)
    })
    const latestImportEvent = GM_getValue(IMPORT_EVENT_STORAGE_KEY, null)
    if (latestImportEvent) window.setTimeout(() => dispatchImportEvent(latestImportEvent), 0)
  }

  function bootProviderBridge (provider) {
    const openTask = async () => {
      if (provider === 'CODEFORCES') {
        const importRequestId = importTaskIdFromHash() || GM_getValue(activeImportStorageKey(provider), '')
        const importTask = importRequestId && GM_getValue(importTaskStorageKey(importRequestId), null)
        if (importTask && importTask.schema === IMPORT_SCHEMA) {
          await bootCodeforcesImport(importTask)
          return
        }
      }
      const task = loadProviderTask(provider)
      if (!task) return
      if (!task.remote_submission_id && (task.adapter_state || {}).phase !== 'JUDGING') {
        publishBridgeEvent(task, 'OPENING', {
          message: `已打开 ${provider} 页面`,
          remote_url: window.location.href.split('#')[0]
        })
      }
      if (provider === 'CODEFORCES') await bootCodeforcesTask(task)
      else if (provider === 'NOWCODER') await bootNowcoderTask(task)
      else if (provider === 'LUOGU') await bootLuoguTask(task)
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', openTask, { once: true })
    } else {
      openTask()
    }
  }

  function announce () {
    if (!document.documentElement) return false
    const provider = currentProvider()
    document.documentElement.setAttribute(READY_ATTRIBUTE, version)
    if (provider) document.documentElement.setAttribute(PROVIDER_ATTRIBUTE, provider)
    window.dispatchEvent(new CustomEvent(READY_EVENT, {
      detail: {
        version,
        provider,
        capabilities: ['bridge-protocol-v1', 'background-submit-v1', 'remote-import-v1', 'provider-tab-detection']
      }
    }))
    return true
  }

  function announceWhenReady () {
    if (announce()) return
    const observer = new MutationObserver(() => {
      if (!announce()) return
      observer.disconnect()
    })
    observer.observe(document, { childList: true, subtree: true })
  }

  window.addEventListener(PING_EVENT, announce)
  const provider = currentProvider()
  if (provider === 'XJU_OJ') bootOjBridge()
  else if (provider) bootProviderBridge(provider)
  announceWhenReady()

  if (typeof GM_registerMenuCommand === 'function') {
    GM_registerMenuCommand('打开 XJU-OJ 远程提交助手', () => {
      GM_openInTab(`${OJ_ORIGIN}/remote-bridge`, { active: true, insert: true })
    })
  }
})()
