import { JUDGE_STATUS } from '@/utils/constants'

export function isSubmissionPending (submission) {
  return [6, 7, 9].includes(Number(submission.result))
}

export function submissionStatus (submission, translate, now = Date.now()) {
  const status = JUDGE_STATUS[String(submission.result)] || JUDGE_STATUS['6']
  const result = { label: translate(`m.${status.name.replace(/ /g, '_')}`), type: status.type || 'info', hint: '' }
  if (submission.judge_mode !== 'REMOTE' || !isSubmissionPending(submission)) return result
  const remote = submission.remote_status
  const action = remote === 'AUTH_REQUIRED' || remote === 'VERIFICATION_REQUIRED'
  const updated = Date.parse(submission.remote_update_time || submission.create_time)
  const stale = Number.isFinite(updated) && now - updated > 180000
  const key = remote === 'AUTH_REQUIRED' ? 'Remote_Login_Required'
    : remote === 'VERIFICATION_REQUIRED' ? 'Remote_Verification_Required'
      : stale ? 'Remote_Result_Stale'
        : submission.remote_submission_id ? 'Remote_Judging' : 'Remote_Submitting'
  return {
    label: translate(`m.${key}`), type: action || stale ? 'warning' : 'info',
    hint: action ? (submission.remote_message || translate(`m.${key}`))
      : translate(`m.${stale ? 'Remote_Result_Stale_Hint' : 'Remote_Keep_Tab_Hint'}`)
  }
}
