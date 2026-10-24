import { apiErrorMessage } from '@/utils/apiError'
import { ElMessage } from 'element-plus'
import store from '@/store'
import axios from 'axios'

axios.defaults.baseURL = '/api'
axios.defaults.xsrfHeaderName = 'X-CSRFToken'
axios.defaults.xsrfCookieName = 'csrftoken'

export default {
  getWebsiteConf (params) {
    return ajax('website', 'get', {
      params
    })
  },
  getAuthProviders () {
    return ajax('auth/providers', 'get')
  },
  getAnnouncementList (offset, limit) {
    let params = {
      offset: offset,
      limit: limit
    }
    return ajax('announcement', 'get', {
      params
    })
  },
  login (data) {
    return ajax('login', 'post', {
      data
    })
  },
  legacyEmailLink (data) {
    return ajax('auth/oidc/legacy-email-link', 'post', { data })
  },
  checkUsernameOrEmail (username, email) {
    return ajax('check_username_or_email', 'post', {
      data: {
        username,
        email
      }
    })
  },
  // 注册
  register (data) {
    return ajax('register', 'post', {
      data
    })
  },
  logout () {
    return ajax('logout', 'get')
  },
  getCaptcha () {
    return ajax('captcha', 'get')
  },
  getUserInfo (username = undefined) {
    return ajax('profile', 'get', {
      params: {
        username
      }
    })
  },
  updateProfile (profile) {
    return ajax('profile', 'put', {
      data: profile
    })
  },
  freshDisplayID (userID) {
    return ajax('profile/fresh_display_id', 'get', {
      params: {
        user_id: userID
      }
    })
  },
  twoFactorAuth (method, data) {
    return ajax('two_factor_auth', method, {
      data
    })
  },
  tfaRequiredCheck (username) {
    return ajax('tfa_required', 'post', {
      data: {
        username
      }
    })
  },
  getSessions () {
    return ajax('sessions', 'get')
  },
  uploadAvatar (formData) {
    return ajax('upload_avatar', 'post', {
      data: formData
    })
  },
  deleteSession (sessionKey) {
    return ajax('sessions', 'delete', {
      params: {
        session_key: sessionKey
      }
    })
  },
  applyResetPassword (data) {
    return ajax('apply_reset_password', 'post', {
      data
    })
  },
  resetPassword (data) {
    return ajax('reset_password', 'post', {
      data
    })
  },
  changePassword (data) {
    return ajax('change_password', 'post', {
      data
    })
  },
  changeEmail (data) {
    return ajax('change_email', 'post', {
      data
    })
  },
  getLanguages () {
    return ajax('languages', 'get')
  },
  getProblemTagList (params) {
    return ajax('problem/tags', 'get', {
      params
    })
  },
  favoriteProblem (problemId) {
    return ajax('problem/favorite', 'post', {
      data: { problem_id: problemId }
    })
  },
  unfavoriteProblem (problemId) {
    return ajax('problem/favorite', 'delete', {
      params: { problem_id: problemId }
    })
  },
  getProfileProblems (params) {
    return ajax('profile/problems', 'get', {
      params
    })
  },
  getProblemList (offset, limit, searchParams) {
    let params = {
      paging: true,
      offset,
      limit
    }
    Object.keys(searchParams).forEach((element) => {
      if (searchParams[element]) {
        params[element] = searchParams[element]
      }
    })
    return ajax('problem', 'get', {
      params: params
    })
  },
  pickone () {
    return ajax('pickone', 'get')
  },
  getProblem (problemID) {
    return ajax('problem', 'get', {
      params: {
        problem_id: problemID
      }
    })
  },
  getContestList (offset, limit, searchParams) {
    let params = {
      offset,
      limit
    }
    if (searchParams !== undefined) {
      Object.keys(searchParams).forEach((element) => {
        if (searchParams[element]) {
          params[element] = searchParams[element]
        }
      })
    }
    return ajax('contests', 'get', {
      params
    })
  },
  getContest (id) {
    return ajax('contest', 'get', {
      params: {
        id
      }
    })
  },
  getContestAccess (contestID) {
    return ajax('contest/access', 'get', {
      params: {
        contest_id: contestID
      }
    })
  },
  checkContestPassword (contestID, password) {
    return ajax('contest/password', 'post', {
      data: {
        contest_id: contestID,
        password
      }
    })
  },
  registerContest (contestID, password = '') {
    return ajax('contest/register', 'post', {
      data: {
        contest_id: contestID,
        password
      }
    })
  },
  getContestAnnouncementList (contestId) {
    return ajax('contest/announcement', 'get', {
      params: {
        contest_id: contestId
      }
    })
  },
  async pollContestAnnouncementList (contestId) {
    const response = await axios.get('contest/announcement', {
      params: { contest_id: contestId },
      timeout: 10000
    })
    if (response.data.error !== null) throw new Error('Contest announcements unavailable')
    return response
  },
  getContestProblemList (contestId) {
    return ajax('contest/problem', 'get', {
      params: {
        contest_id: contestId
      }
    })
  },
  getContestProblem (problemID, contestID) {
    return ajax('contest/problem', 'get', {
      params: {
        contest_id: contestID,
        problem_id: problemID
      }
    })
  },
  submitCode (data) {
    return ajax('submission', 'post', {
      data
    })
  },
  updateRemoteSubmission (data) {
    return ajax('remote_submission/event', 'post', {
      data
    })
  },
  recoverRemoteSubmission (submissionId) {
    return ajax('remote_submission/recover', 'get', { params: { submission_id: submissionId } })
  },
  getSubmissionList (offset, limit, params) {
    params.limit = limit
    params.offset = offset
    return ajax('submissions', 'get', {
      params
    })
  },
  getContestSubmissionList (offset, limit, params) {
    params.limit = limit
    params.offset = offset
    return ajax('contest_submissions', 'get', {
      params
    })
  },
  getSubmission (id) {
    return ajax('submission', 'get', {
      params: {
        id
      }
    })
  },
  submissionExists (problemID) {
    return ajax('submission_exists', 'get', {
      params: {
        problem_id: problemID
      }
    })
  },
  submissionRejudge (id) {
    return ajax('admin/submission/rejudge', 'post', {
      data: {
        id
      }
    })
  },
  updateSubmission (data) {
    return ajax('submission', 'put', {
      data
    })
  },
  getUserRank (offset, limit, rule = 'acm') {
    let params = {
      offset,
      limit,
      rule
    }
    return ajax('user_rank', 'get', {
      params
    })
  },
  getContestRank (params) {
    return ajax('contest_rank', 'get', {
      params
    })
  },
  // Contest preparation workspace (creator, problem setters and verifiers).
  // Creating one is an admin action, so it reuses the admin contest endpoint.
  createPrepContest (data) {
    return ajax('admin/contest', 'post', {
      data: { ...data, preparation: true }
    })
  },
  setPrepContestState (contestId, state) {
    return ajax('contest/prep/state', 'put', {
      data: { contest_id: contestId, state }
    })
  },
  getPrepMembers (contestId) {
    return ajax('contest/prep/members', 'get', {
      params: { contest_id: contestId }
    })
  },
  addPrepMember (contestId, username, role) {
    return ajax('contest/prep/members', 'post', {
      data: { contest_id: contestId, username, role }
    })
  },
  updatePrepMember (contestId, userId, role) {
    return ajax('contest/prep/members', 'put', {
      data: { contest_id: contestId, user_id: userId, role }
    })
  },
  removePrepMember (contestId, userId) {
    return ajax('contest/prep/members', 'delete', {
      params: { contest_id: contestId, user_id: userId }
    })
  },
  searchPrepUsers (contestId, keyword) {
    return ajax('contest/prep/members/search', 'get', {
      params: { contest_id: contestId, keyword }
    })
  },
  getPrepProblems (contestId) {
    return ajax('contest/prep/problem', 'get', {
      params: { contest_id: contestId }
    })
  },
  getPrepProblem (contestId, problemId) {
    return ajax('contest/prep/problem', 'get', {
      params: { contest_id: contestId, id: problemId }
    })
  },
  createPrepProblem (data) {
    return ajax('contest/prep/problem', 'post', {
      data
    })
  },
  editPrepProblem (data) {
    return ajax('contest/prep/problem', 'put', {
      data
    })
  },
  deletePrepProblem (contestId, problemId) {
    return ajax('contest/prep/problem', 'delete', {
      params: { contest_id: contestId, id: problemId }
    })
  },
  setPrepProblemVisible (contestId, problemId, visible) {
    return ajax('contest/prep/problem/visible', 'put', {
      data: { contest_id: contestId, id: problemId, visible }
    })
  },
  addPrepProblemFromPublic (contestId, problemId) {
    return ajax('contest/prep/problem/from_public', 'post', {
      data: { contest_id: contestId, problem_id: problemId }
    })
  },
  reorderPrepProblems (contestId, problemIds) {
    return ajax('contest/prep/problem/order', 'put', {
      data: { contest_id: contestId, problem_ids: problemIds }
    })
  },
  compilePrepSPJ (data) {
    return ajax('contest/prep/compile_spj', 'post', {
      data
    })
  },
  publishPrepContest (data) {
    return ajax('contest/prep/publish', 'post', {
      data
    })
  },
  getPrepRank (contestId) {
    return ajax('contest/prep/rank', 'get', {
      params: { contest_id: contestId }
    })
  },
  getPrepFeedback (contestId, problemId) {
    return ajax('contest/prep/feedback', 'get', {
      params: { contest_id: contestId, problem_id: problemId }
    })
  },
  addPrepFeedback (contestId, problemId, content) {
    return ajax('contest/prep/feedback', 'post', {
      data: { contest_id: contestId, problem_id: problemId, content }
    })
  },
  setPrepFeedbackResolved (contestId, id, resolved) {
    return ajax('contest/prep/feedback', 'put', {
      data: { contest_id: contestId, id, resolved }
    })
  },
  getPrepInvites (contestId) {
    return ajax('contest/prep/invite', 'get', {
      params: { contest_id: contestId }
    })
  },
  createPrepInvite (contestId, role) {
    return ajax('contest/prep/invite', 'post', {
      data: { contest_id: contestId, role }
    })
  },
  // Revokes one link by id, or every unused link of the contest.
  revokePrepInvites (contestId, id) {
    return ajax('contest/prep/invite', 'delete', {
      params: id ? { contest_id: contestId, id } : { contest_id: contestId }
    })
  },
  acceptPrepInvite (token) {
    return ajax('contest/prep/invite/accept', 'post', {
      data: { token }
    })
  },
  deletePrepFeedback (contestId, id) {
    return ajax('contest/prep/feedback', 'delete', {
      params: { contest_id: contestId, id }
    })
  },
  getACMACInfo (params) {
    return ajax('admin/contest/acm_helper', 'get', {
      params
    })
  },
  updateACInfoCheckedStatus (data) {
    return ajax('admin/contest/acm_helper', 'put', {
      data
    })
  }
}

/**
 * @param url
 * @param method get|post|put|delete...
 * @param params like queryString. if a url is index?a=1&b=2, params = {a: '1', b: '2'}
 * @param data post data, use for method put|post
 * @returns {Promise}
 */
function ajax (url, method, options) {
  if (options !== undefined) {
    var {params = {}, data = {}} = options
  } else {
    params = data = {}
  }
  return new Promise((resolve, reject) => {
    axios({
      url,
      method,
      params,
      data
    }).then(res => {
      // API正常返回(status=20x), 是否错误通过有无error判断
      if (res.data?.error !== null) {
        ElMessage.error(apiErrorMessage(res))
        reject(res)
        // 若后端返回为登录，则为session失效，应退出当前登录用户
        if (apiErrorMessage(res).startsWith('Please login')) {
          store.dispatch('changeModalStatus', {'mode': 'login', 'visible': true})
        }
      } else {
        resolve(res)
        // if (method !== 'get') {
        //   ElMessage.success('Succeeded')
        // }
      }
    }, res => {
      // API请求异常，一般为Server error 或 network error
      reject(res)
      ElMessage.error(apiErrorMessage(res))
    })
  })
}
