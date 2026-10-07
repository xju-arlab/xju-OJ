import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const source = await fs.readFile(new URL('../src/pages/oj/submissionStatus.js', import.meta.url), 'utf8')
const constants = new URL('../src/utils/constants.js', import.meta.url).href
const { submissionStatus, isSubmissionPending } = await import(`data:text/javascript;base64,${Buffer.from(source.replace("'@/utils/constants'", JSON.stringify(constants))).toString('base64')}`)
const t = key => key
const pending = { result: 6, judge_mode: 'REMOTE', create_time: '2026-09-13T06:00:00Z' }
assert.equal(submissionStatus({ ...pending, remote_status: 'AUTH_REQUIRED' }, t).label, 'm.Remote_Login_Required')
assert.equal(submissionStatus({ ...pending, remote_status: 'VERIFICATION_REQUIRED' }, t).label, 'm.Remote_Verification_Required')
assert.equal(submissionStatus({ ...pending, result: 7, remote_status: 'JUDGING' }, t).label, 'm.Remote_Result_Stale')
assert.equal(submissionStatus({ ...pending, result: 7, remote_status: 'JUDGING', remote_submission_id: '1', remote_update_time: new Date().toISOString() }, t).label, 'm.Remote_Judging')
assert.equal(submissionStatus({ ...pending, result: 0, remote_status: 'FINISHED' }, t).label, 'm.Accepted')
assert.equal(submissionStatus({ ...pending, judge_mode: 'LOCAL' }, t).label, 'm.Pending')
assert.equal(isSubmissionPending({ result: '7' }), true)
assert.equal(isSubmissionPending({ result: -2 }), false)
console.log('submission state presentation passed')
