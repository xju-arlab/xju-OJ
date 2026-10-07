'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const userscriptPath = path.resolve(
  __dirname,
  '../static/userscripts/xju-oj-remote-bridge.user.js'
)
const source = fs.readFileSync(userscriptPath, 'utf8')
const frontendBridge = fs.readFileSync(
  path.resolve(__dirname, '../src/pages/oj/remoteBridge.js'),
  'utf8'
)
const problemPage = fs.readFileSync(
  path.resolve(__dirname, '../src/pages/oj/views/problem/Problem.vue'),
  'utf8'
)
const bridgeInstallPage = fs.readFileSync(
  path.resolve(__dirname, '../src/pages/oj/views/help/RemoteBridge.vue'),
  'utf8'
)

function section (startMarker, endMarker) {
  const start = source.indexOf(startMarker)
  assert.notEqual(start, -1, `missing marker: ${startMarker}`)
  const end = source.indexOf(endMarker, start + startMarker.length)
  assert.notEqual(end, -1, `missing marker: ${endMarker}`)
  return source.slice(start, end)
}

assert.match(source, /^\/\/ @version\s+1\.1\.0$/m)
assert.match(frontendBridge, /MINIMUM_BRIDGE_VERSION = \[1, 1, 0\]/)
assert.match(frontendBridge, /export function requestRemoteBridgeStatus/)
assert.match(frontendBridge, /export function subscribeRemoteBridgeReady/)
assert.match(bridgeInstallPage, /@click="beginUserscriptActivation"/)
assert.match(bridgeInstallPage, /document\.addEventListener\('visibilitychange', this\.handleActivationReturn\)/)
assert.match(bridgeInstallPage, /window\.location\.reload\(\)/)

const opener = section(
  'function openProviderActionTab',
  'function codeforcesImportTarget'
)
assert.match(opener, /status !== 'AUTH_REQUIRED'/)
assert.match(opener, /status !== 'VERIFICATION_REQUIRED'/)
assert.match(opener, /GM_openInTab\(task\.target_url/)
assert.match(opener, /backgroundCloudflare/)
assert.match(opener, /active: !backgroundCloudflare/)

const runner = section(
  'async function runRemoteTaskFromOj',
  'async function startRemoteTask'
)
for (const provider of ['CODEFORCES', 'NOWCODER', 'LUOGU']) {
  assert.match(runner, new RegExp(`task\\.provider === '${provider}'`))
}

const submitEntry = section(
  'async function startRemoteTask',
  'function startRemoteImport'
)
assert.match(submitEntry, /await runRemoteTaskFromOj\(task\)/)
assert.doesNotMatch(submitEntry, /GM_openInTab/)

assert.match(source, /submitCodeforcesFromOj/)
assert.match(source, /window\._cf_chl_opt/)
assert.doesNotMatch(source, /Boolean\(root\.querySelector\('\.g-recaptcha, \[data-sitekey\]/)
assert.match(source, /submitNowcoderDirect/)
assert.match(source, /submitLuoguDirect/)
assert.match(source, /payload && payload\.currentData/)
assert.match(source, /luoguDerivedVerdict/)
assert.match(source, /isRemoteConnectionError/)
assert.match(source, /openProviderRetryTab/)
assert.match(source, /GM_listValues/)
assert.match(source, /backendEventQueues/)
assert.match(source, /for \(const provider of \['CODEFORCES', 'NOWCODER', 'LUOGU'\]\)/)

const remoteEventHandler = problemPage.slice(
  problemPage.indexOf('handleRemoteBridgeEvent'),
  problemPage.indexOf('onResetToTemplate')
)
assert.doesNotMatch(remoteEventHandler, /updateRemoteSubmission/)
assert.match(problemPage, /showAcceptedCelebration\(\)\.then\(\(\) => this\.finishSubmissionStatus\(result, id\)\)/)
assert.match(problemPage, /finishSubmissionStatus \(result, submissionId\)[\s\S]*this\.result = result/)

console.log('remote bridge contract passed')
