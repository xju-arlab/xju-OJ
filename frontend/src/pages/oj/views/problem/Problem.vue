<template>
  <div class="problem-page-root">
  <ContestAnnouncementBanner v-if="canReadAnnouncements" :key="contestID" :contest-id="contestID" />
  <div v-if="problemLoaded" class="problem-workspace">
    <div id="problem-main">
      <!--problem main-->
      <Panel :padding="40" shadow>
        <template #title><div class="problem-title-header">
          <div class="problem-title-copy">
            <small>Problem {{problem._id}}</small>
            <div class="problem-title-line">
              <strong>{{problem.title}}</strong>
              <div v-if="publicProblemTags.length" class="problem-title-tags" :aria-label="$t('m.Tags')">
                <span v-for="(tag, index) in publicProblemTags" :key="`${tag}-${index}`" :title="tag">{{tag}}</span>
              </div>
            </div>
          </div>
          <button v-if="contestID"
                  type="button"
                  class="problem-header-action"
                  @click="handleRoute({name: 'contest-problem-list', params: {contestID: contestID}})">
            <Icon type="arrow-left" />
            <span>{{$t('m.Problems_List')}}</span>
          </button>
        </div></template>
        <div id="problem-content" class="markdown-body" v-katex v-highlight>
          <div class="problem-brief" aria-label="Problem information">
            <div><span>{{$t('m.Time_Limit')}}</span><strong>{{problem.time_limit}} MS</strong></div>
            <div><span>{{$t('m.Memory_Limit')}}</span><strong>{{problem.memory_limit}} MB</strong></div>
            <div class="problem-level-item">
              <span>{{$t('m.Level')}}</span>
              <strong v-if="contestID" class="problem-level-empty">-</strong>
              <strong v-else-if="problem.difficulty"
                      :class="['problem-level-badge', `difficulty-${problem.difficulty.toLowerCase()}`]">
                {{$t('m.Difficulty_' + problem.difficulty)}}
              </strong>
              <strong v-else class="problem-level-empty">-</strong>
            </div>
          </div>

          <p class="title">{{$t('m.Description')}}</p>
          <div class="content" v-html=problem.description></div>
          <!-- {{$t('m.music')}} -->
          <p class="title">{{$t('m.Input')}} <span v-if="problem.io_mode.io_mode=='File IO'">({{$t('m.FromFile')}}: {{ problem.io_mode.input }})</span></p>
          <div class="content" v-html=problem.input_description></div>

          <p class="title">{{$t('m.Output')}} <span v-if="problem.io_mode.io_mode=='File IO'">({{$t('m.ToFile')}}: {{ problem.io_mode.output }})</span></p>
          <div class="content" v-html=problem.output_description></div>

          <div v-for="(sample, index) of problem.samples" :key="index">
            <div class="flex-container sample">
              <div class="sample-input">
                <p class="title">{{$t('m.Sample_Input')}} {{index + 1}}
                  <a class="copy"
                     role="button"
                     tabindex="0"
                     @click="copySample(sample.input)"
                     @keydown.enter.prevent="copySample(sample.input)">
                    <Icon type="clipboard"></Icon>
                  </a>
                </p>
                <pre>{{sample.input}}</pre>
              </div>
              <div class="sample-output">
                <p class="title">{{$t('m.Sample_Output')}} {{index + 1}}</p>
                <pre>{{sample.output}}</pre>
              </div>
            </div>
          </div>

          <div v-if="problem.hint">
            <p class="title">{{$t('m.Hint')}}</p>
            <Card dis-hover>
              <div class="content" v-html=problem.hint></div>
            </Card>
          </div>

          <div v-if="problem.source">
            <p class="title">{{$t('m.Source')}}</p>
            <p class="content">{{problem.source}}</p>
          </div>

        </div>
      </Panel>
      <!--problem main end-->
    </div>

    <div id="solution-column">
      <section id="submit-code" aria-labelledby="solution-title">
        <h2 id="solution-title" class="visually-hidden">{{$t('m.Submit')}}</h2>
        <CodeMirror :value="code" @update:value="code = $event"
                    :languages="problem.languages"
                    :language="language"
                    :theme="theme"
                    @resetCode="onResetToTemplate"
                    @changeTheme="onChangeTheme"
                    @changeLang="onChangeLang"></CodeMirror>
        <div class="submit-dock">
          <div class="submit-feedback">
            <div class="status" v-if="statusVisible">
              <template v-if="!this.contestID || (this.contestID && OIContestRealTimePermission)">
                <span>{{$t('m.Status')}}</span>
                <button type="button"
                        :class="['judge-status-badge', 'submission-status-link', `is-${submissionStatus.type}`]"
                        @click="handleRoute('/status/'+submissionId)">
                  {{$t('m.' + submissionStatus.text.replace(/ /g, "_"))}}
                </button>
              </template>
              <template v-else-if="this.contestID && !OIContestRealTimePermission">
                <Alert type="success" show-icon>{{$t('m.Submitted_successfully')}}</Alert>
              </template>
            </div>
            <div v-else-if="problem.my_status === 0">
              <Alert type="success" show-icon>{{$t('m.You_have_solved_the_problem')}}</Alert>
            </div>
            <div v-else-if="this.contestID && !OIContestRealTimePermission && submissionExists">
              <Alert type="success" show-icon>{{$t('m.You_have_submitted_a_solution')}}</Alert>
            </div>
            <div v-if="contestEnded && !statusVisible">
              <Alert type="info" show-icon>{{$t('m.Contest_Practice_Notice')}}</Alert>
            </div>
          </div>

          <div class="submit-controls">
            <div v-if="captchaRequired" class="captcha-container">
              <Tooltip :content="$t('m.Click_to_Refresh')" placement="top"><img :src="captchaSrc" @click="getCaptchaSrc"/></Tooltip>
              <Input v-model="captchaCode" class="captcha-code" />
            </div>
            <LegacyButton type="primary" @click="submitCode"
                    :disabled="problemSubmitDisabled || submitted || submitting"
                    :class="['oj-submit-button', { 'is-loading': submitting, 'is-success': submitted }]">
              <Icon v-if="submitting" type="loading" class="submit-spinner" />
              <Icon v-else-if="submitted" type="check" />
              <Icon v-else type="send" />
              <span v-if="submitting">{{$t('m.Submitting')}}</span>
              <span v-else-if="submitted">{{$t('m.Submitted_successfully')}}</span>
              <span v-else>{{contestEnded ? $t('m.Submit_Practice') : $t('m.Submit')}}</span>
            </LegacyButton>
          </div>
        </div>
      </section>

      <section class="recent-submission-card" aria-labelledby="recent-submissions-title">
        <button type="button" class="recent-submission-header" @click="handleRoute(submissionRoute)">
          <span id="recent-submissions-title" class="recent-submission-heading">
            <Icon type="navicon-round"></Icon>
            <span>{{$t('m.Submissions')}}</span>
          </span>
          <Icon type="arrow-down-b" class="recent-submission-arrow"></Icon>
        </button>
        <div class="recent-submission-divider"></div>
        <div class="recent-submission-list">
          <div v-for="submission in recentSubmissions" :key="submission.id" class="recent-submission-row">
            <span class="recent-submission-main">
              <strong>{{submission.username}}</strong>
              <small>{{submission.language}}</small>
            </span>
            <span :class="['judge-status-badge', submissionStatusClass(submission)]">
              {{submissionStatusLabel(submission)}}
            </span>
            <time>{{formatSubmissionTime(submission.create_time)}}</time>
          </div>
          <div v-if="!recentSubmissions.length" class="recent-submission-empty">{{ $t('m.No_Recent_Submissions') }}</div>
        </div>
      </section>

    </div>

  </div>
  <div v-else class="problem-loading"><Spin size="large" /></div>

  <Teleport to="body">
    <Transition name="accepted-celebration" @after-leave="completeAcceptedCelebration">
      <div v-if="acceptedCelebrationVisible"
           class="accepted-celebration-overlay"
           role="status"
           aria-live="assertive"
           @click.self="hideAcceptedCelebration">
        <section :key="acceptedCelebrationKey" class="accepted-celebration-card" aria-label="Accepted">
          <button type="button"
                  class="accepted-celebration-close"
                  :aria-label="$t('m.Close')"
                  @click="hideAcceptedCelebration">
            <Icon type="close" />
          </button>
          <div class="accepted-burst" aria-hidden="true">
            <span v-for="particle in 12" :key="particle" :class="`particle-${particle}`"></span>
            <div class="accepted-check"><Icon type="check" /></div>
          </div>
          <p class="accepted-eyebrow">XJU-OJ</p>
          <strong>Accepted!</strong>
          <span class="accepted-problem-title">{{problem.title}}</span>
        </section>
      </div>
    </Transition>
  </Teleport>
  </div>
</template>
<script>
  import {mapGetters, mapActions} from '@/store/compat'
  import {types} from '../../../../store'
  import CodeMirror from '@oj/components/CodeMirror.vue'
  import storage from '@/utils/storage'
  import {FormMixin} from '@oj/components/mixins'
  import {JUDGE_STATUS, CONTEST_STATUS, buildProblemCodeKey} from '@/utils/constants'
  import api from '@oj/api'
  import ContestAnnouncementBanner from '@oj/components/ContestAnnouncementBanner.vue'
  import { dispatchRemoteSubmission, isRemoteBridgeInstalled, subscribeRemoteBridgeEvents } from '@oj/remoteBridge'
  import { applyDevelopmentProblemFixture, cloneFixtures, MOCK_PROBLEMS, MOCK_SUBMISSIONS } from '@oj/mocks/fixtures'

  const DEFAULT_PROBLEM_LANGUAGE = 'C++'
  const selectDefaultProblemLanguage = (languages) => {
    const supportedLanguages = Array.isArray(languages) ? languages : []
    return supportedLanguages.includes(DEFAULT_PROBLEM_LANGUAGE)
      ? DEFAULT_PROBLEM_LANGUAGE
      : (supportedLanguages[0] || DEFAULT_PROBLEM_LANGUAGE)
  }

  export default {
    name: 'Problem',
    components: {
      CodeMirror, ContestAnnouncementBanner
    },
    mixins: [FormMixin],
    data () {
      return {
        statusVisible: false,
        captchaRequired: false,
        submissionExists: false,
        captchaCode: '',
        captchaSrc: '',
        contestID: '',
        problemID: '',
        submitting: false,
        code: '',
        language: DEFAULT_PROBLEM_LANGUAGE,
        theme: 'solarized',
        submissionId: '',
        submitted: false,
        acceptedCelebrationVisible: false,
        acceptedCelebrationKey: 0,
        acceptedCelebrationTimer: null,
        acceptedCelebrationResolve: null,
        problemCodeSaveTimer: null,
        remoteBridgeUnsubscribe: null,
        remoteNoticeStatus: '',
        problemLoaded: false,
        recentSubmissions: [],
        result: {
          result: 9
        },
        problem: {
          title: '',
          description: '',
          hint: '',
          my_status: '',
          template: {},
          languages: [],
          created_by: {
            username: ''
          },
          tags: [],
          io_mode: {'io_mode': 'Standard IO'}
        }
      }
    },
    mounted () {
      this.remoteBridgeUnsubscribe = subscribeRemoteBridgeEvents(this.handleRemoteBridgeEvent)
      this.loadProblemCode(this.$route.params.problemID, this.$route.params.contestID)
      window.addEventListener('pagehide', this.handlePageExit)
      window.addEventListener('beforeunload', this.handlePageExit)
      this.$store.commit(types.CHANGE_CONTEST_ITEM_VISIBLE, {menu: false})
      this.init()
    },
    methods: {
      ...mapActions(['changeDomTitle']),
      loadProblemCode (problemID, contestID) {
        const problemCode = storage.get(buildProblemCodeKey(problemID, contestID))
        this.code = problemCode && typeof problemCode.code === 'string' ? problemCode.code : ''
        this.language = (problemCode && problemCode.language) || DEFAULT_PROBLEM_LANGUAGE
        this.theme = (problemCode && problemCode.theme) || 'solarized'
      },
      persistProblemCode (problemID = this.problemID || this.$route.params.problemID,
        contestID = this.contestID || this.$route.params.contestID) {
        clearTimeout(this.problemCodeSaveTimer)
        this.problemCodeSaveTimer = null
        if (!problemID) return
        storage.set(buildProblemCodeKey(problemID, contestID), {
          code: this.code,
          language: this.language,
          theme: this.theme,
          updated_at: Date.now()
        })
      },
      scheduleProblemCodeSave () {
        clearTimeout(this.problemCodeSaveTimer)
        this.problemCodeSaveTimer = setTimeout(() => this.persistProblemCode(), 300)
      },
      handlePageExit () {
        this.persistProblemCode()
      },
      init (route = this.$route) {
        this.$Loading.start()
        this.problemLoaded = false
        this.contestID = route.params.contestID
        this.problemID = route.params.problemID
        let func = route.name === 'problem-details' ? 'getProblem' : 'getContestProblem'
        api[func](this.problemID, this.contestID).then(res => {
          const problem = applyDevelopmentProblemFixture(res.data.data)
          if (problem) this.applyProblem(problem)
          else this.$Loading.error()
        }).catch(() => {
          const fallback = MOCK_PROBLEMS.find(problem => String(problem._id) === String(this.problemID))
          if (fallback) {
            this.applyProblem(cloneFixtures([fallback])[0])
          } else {
            this.$Loading.error()
          }
        })
      },
      applyProblem (problem) {
        this.$Loading.finish()
        this.changeDomTitle({title: problem.title})
        api.submissionExists(problem.id).then(res => {
          this.submissionExists = res.data.data
        }).catch(() => {
          this.submissionExists = false
        })
        const fixture = MOCK_PROBLEMS.find(item => String(item._id) === String(problem._id))
        if (fixture) {
          // Older API serializers may return template keys with empty values
          // when no PREPEND/TEMPLATE markers are stored. Keep real API fields,
          // but provide the matching local starter code so the editor remains
          // useful in development and theme previews always have code to show.
          const apiTemplates = Object.fromEntries(Object.entries(problem.template || {}).filter(([, value]) => value))
          problem.template = { ...cloneFixtures([fixture])[0].template, ...apiTemplates }
          if (!problem.languages || !problem.languages.length) problem.languages = fixture.languages.slice()
        }
        problem.languages = (problem.languages || []).slice().sort()
        this.problem = problem
        this.loadRecentSubmissions(problem._id)
        this.problemLoaded = true

        // 在beforeRouteEnter中修改了, 说明本地有code，无需加载template
        if (this.code !== '') {
          return
        }
        // try to load problem template
        this.language = selectDefaultProblemLanguage(this.problem.languages)
        let template = this.problem.template
        if (template && template[this.language]) {
          this.code = template[this.language]
        }
      },
      handleRoute (route) {
        this.$router.push(route)
      },
      onChangeLang (newLang) {
        if (this.problem.template[newLang]) {
          if (this.code.trim() === '') {
            this.code = this.problem.template[newLang]
          }
        }
        this.language = newLang
      },
      onChangeTheme (newTheme) {
        this.theme = newTheme
      },
      loadRecentSubmissions (problemID) {
        const params = { problem_id: problemID }
        const method = this.contestID ? 'getContestSubmissionList' : 'getSubmissionList'
        if (this.contestID) {
          params.contest_id = this.contestID
          params.myself = '1'
        }
        api[method](0, 5, params).then(res => {
          const data = res.data.data || {}
          const results = Array.isArray(data.results) ? data.results : []
          this.recentSubmissions = results.length
            ? results.slice().sort((a, b) => new Date(b.create_time) - new Date(a.create_time)).slice(0, 5)
            : this.mockSubmissions(problemID)
        }).catch(() => {
          this.recentSubmissions = this.mockSubmissions(problemID)
        })
      },
      mockSubmissions (problemID) {
        const submissions = MOCK_SUBMISSIONS.filter(item => String(item.problem) === String(problemID))
        const visibleSubmissions = this.contestID
          ? submissions.filter(item => item.username === this.user?.username)
          : submissions
        return cloneFixtures(visibleSubmissions)
      },
      submissionStatusLabel (submission) {
        const status = JUDGE_STATUS[String(submission.result)] || {}
        const statusName = status.name || 'Pending'
        return this.$t(`m.${statusName.replace(/ /g, '_')}`)
      },
      submissionStatusClass (submission) {
        const status = JUDGE_STATUS[String(submission.result)] || {}
        return `is-${status.type || 'info'}`
      },
      formatSubmissionTime (value) {
        if (!value) return ''
        return this.$filters.localtime(value, 'MMM D HH:mm')
      },
      handleRemoteBridgeEvent (payload) {
        if (!payload || String(payload.submission_id) !== String(this.submissionId)) return
        if (payload.status === 'AUTH_REQUIRED' && this.remoteNoticeStatus !== payload.status) {
          this.remoteNoticeStatus = payload.status
          this.$Modal.info({
            title: this.$t('m.Remote_Bridge_Account_Required_Title'),
            content: this.$t('m.Remote_Bridge_Account_Required')
          })
        } else if (payload.status === 'VERIFICATION_REQUIRED' && this.remoteNoticeStatus !== payload.status) {
          this.remoteNoticeStatus = payload.status
          this.$Modal.info({
            title: this.$t('m.Remote_Bridge_Verification_Title'),
            content: this.$t('m.Remote_Bridge_Verification')
          })
        } else if (payload.status === 'FAILED') {
          this.$error(payload.message || this.$t('m.Remote_Bridge_Submit_Failed'))
        }
      },
      onResetToTemplate () {
        this.$Modal.confirm({
          content: this.$t('m.Are_you_sure_you_want_to_reset_your_code'),
          onOk: () => {
            let template = this.problem.template
            if (template && template[this.language]) {
              this.code = template[this.language]
            } else {
              this.code = ''
            }
          }
        })
      },
      checkSubmissionStatus () {
        // 使用setTimeout避免一些问题
        if (this.refreshStatus) {
          // 如果之前的提交状态检查还没有停止,则停止,否则将会失去timeout的引用造成无限请求
          clearTimeout(this.refreshStatus)
        }
        const checkStatus = () => {
          let id = this.submissionId
          api.getSubmission(id).then(res => {
            const result = res.data.data || {}
            const statisticInfo = result.statistic_info || {}
            const isPending = ['6', '7', '9'].includes(String(result.result))
            if (!isPending || Object.keys(statisticInfo).length !== 0) {
              clearTimeout(this.refreshStatus)
              if (Number(result.result) === 0) {
                this.showAcceptedCelebration().then(() => this.finishSubmissionStatus(result, id))
              } else {
                this.finishSubmissionStatus(result, id)
              }
            } else {
              this.result = result
              this.refreshStatus = setTimeout(checkStatus, 2000)
            }
          }, res => {
            this.submitting = false
            this.submitted = false
            clearTimeout(this.refreshStatus)
          })
        }
        this.refreshStatus = setTimeout(checkStatus, 2000)
      },
      submitCode () {
        if (this.code.trim() === '') {
          this.$error(this.$t('m.Code_can_not_be_empty'))
          return
        }
        if (this.problem.judge_mode === 'REMOTE' && !isRemoteBridgeInstalled()) {
          this.$Modal.confirm({
            title: this.$t('m.Remote_Bridge_Missing_Title'),
            content: this.$t('m.Remote_Bridge_Missing_Submit'),
            onOk: () => window.open('/remote-bridge', '_blank', 'noopener,noreferrer')
          })
          return
        }
        this.submissionId = ''
        this.result = {result: 9}
        this.remoteNoticeStatus = ''
        this.hideAcceptedCelebration()
        this.submitting = true
        let data = {
          problem_id: this.problem.id,
          language: this.language,
          code: this.code,
          contest_id: this.contestID
        }
        if (this.captchaRequired) {
          data.captcha = this.captchaCode
        }
        const submitFunc = (data, detailsVisible) => {
          this.statusVisible = true
          api.submitCode(data).then(res => {
            const responseData = res.data.data || {}
            this.submissionId = responseData.submission_id
            this.loadRecentSubmissions(this.problemID)
            if (responseData.remote_task) {
              dispatchRemoteSubmission(responseData.remote_task, data.code)
            }
            // 定时检查状态
            this.submitting = false
            this.submissionExists = true
            if (!detailsVisible) {
              this.$Modal.success({
                title: this.$t('m.Success'),
                content: this.$t('m.Submit_code_successfully')
              })
              return
            }
            this.submitted = true
            this.checkSubmissionStatus()
          }, res => {
            this.getCaptchaSrc()
            if (res.data.data.startsWith('Captcha is required')) {
              this.captchaRequired = true
            }
            this.submitting = false
            this.statusVisible = false
          })
        }

        if (this.contestRuleType === 'OI' && !this.OIContestRealTimePermission) {
          if (this.submissionExists) {
            this.$Modal.confirm({
              title: '',
              content: '<h3>' + this.$t('m.You_have_submission_in_this_problem_sure_to_cover_it') + '<h3>',
              onOk: () => {
                // 暂时解决对话框与后面提示对话框冲突的问题(否则一闪而过）
                setTimeout(() => {
                  submitFunc(data, false)
                }, 1000)
              },
              onCancel: () => {
                this.submitting = false
              }
            })
          } else {
            submitFunc(data, false)
          }
        } else {
          submitFunc(data, true)
        }
      },
      onCopy (event) {
        this.$success('Code copied')
      },
      onCopyError (e) {
        this.$error('Failed to copy code')
      },
      copySample (text) {
        Promise.resolve().then(() => this.$copyText(text)).then(this.onCopy).catch(this.onCopyError)
      },
      showAcceptedCelebration () {
        clearTimeout(this.acceptedCelebrationTimer)
        this.completeAcceptedCelebration()
        this.acceptedCelebrationKey += 1
        this.acceptedCelebrationVisible = true
        const completion = new Promise(resolve => {
          this.acceptedCelebrationResolve = resolve
        })
        this.acceptedCelebrationTimer = setTimeout(this.hideAcceptedCelebration, 2400)
        return completion
      },
      hideAcceptedCelebration () {
        clearTimeout(this.acceptedCelebrationTimer)
        this.acceptedCelebrationVisible = false
      },
      completeAcceptedCelebration () {
        const resolve = this.acceptedCelebrationResolve
        this.acceptedCelebrationResolve = null
        if (resolve) resolve()
      },
      finishSubmissionStatus (result, submissionId) {
        if (String(submissionId) !== String(this.submissionId)) return
        this.result = result
        this.submitting = false
        this.submitted = false
        this.init()
      }
    },
    computed: {
      ...mapGetters(['problemSubmitDisabled', 'contestRuleType', 'OIContestRealTimePermission', 'contestStatus', 'user', 'isAuthenticated', 'contestMenuDisabled', 'isContestAdmin']),
      contest () {
        return this.$store.state.contest.contest
      },
      canReadAnnouncements () {
        if (!this.contestID || !this.isAuthenticated || String(this.contest.id) !== String(this.contestID)) return false
        return !this.contestMenuDisabled && (this.contestStatus !== CONTEST_STATUS.NOT_START || this.isContestAdmin)
      },
      contestEnded () {
        return this.contestStatus === CONTEST_STATUS.ENDED
      },
      publicProblemTags () {
        if (this.contestID) return []
        return (this.problem.tags || []).map(tag => typeof tag === 'string' ? tag : tag.name).filter(Boolean)
      },
      submissionStatus () {
        const status = JUDGE_STATUS[this.result.result] || JUDGE_STATUS['6']
        return {
          text: status.name,
          type: status.type || 'info'
        }
      },
      submissionRoute () {
        if (this.contestID) {
          return {name: 'contest-submission-list', query: {problemID: this.problemID, myself: '1'}}
        } else {
          return {name: 'submission-list', query: {problemID: this.problemID}}
        }
      }
    },
    beforeRouteLeave (to, from) {
      // 防止切换组件后仍然不断请求
      clearTimeout(this.refreshStatus)
      clearTimeout(this.acceptedCelebrationTimer)

      this.$store.commit(types.CHANGE_CONTEST_ITEM_VISIBLE, {menu: true})
      this.persistProblemCode(from.params.problemID, from.params.contestID || null)
    },
    beforeRouteUpdate (to, from) {
      this.persistProblemCode(from.params.problemID, from.params.contestID || null)
      this.loadProblemCode(to.params.problemID, to.params.contestID)
      this.init(to)
    },
    beforeUnmount () {
      clearTimeout(this.refreshStatus)
      clearTimeout(this.acceptedCelebrationTimer)
      this.persistProblemCode()
      window.removeEventListener('pagehide', this.handlePageExit)
      window.removeEventListener('beforeunload', this.handlePageExit)
      if (this.remoteBridgeUnsubscribe) this.remoteBridgeUnsubscribe()
    },
    watch: {
      code () {
        this.scheduleProblemCodeSave()
      },
      language () {
        this.scheduleProblemCodeSave()
      },
      theme () {
        this.scheduleProblemCodeSave()
      }
    }
  }
</script>

<style lang="less" scoped>
  .problem-page-root { width: 100%; }
  .accepted-celebration-overlay {
    position: fixed;
    z-index: 3000;
    inset: 0;
    display: grid;
    place-items: center;
    padding: 20px;
    background: rgba(55, 53, 47, .16);
    backdrop-filter: blur(2px);
  }
  .accepted-celebration-card {
    position: relative;
    display: flex;
    width: min(340px, calc(100vw - 40px));
    min-height: 300px;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    overflow: hidden;
    padding: 34px 28px 30px;
    border: 1px solid rgba(15, 123, 108, .2);
    border-radius: var(--radius-lg);
    background:
      radial-gradient(circle at 50% 22%, rgba(15, 123, 108, .12), transparent 34%),
      var(--color-bg);
    box-shadow: 0 24px 70px rgba(55, 53, 47, .2);
    text-align: center;
    animation: accepted-card-pop 420ms cubic-bezier(.2, .9, .24, 1.18) both;
  }
  .accepted-celebration-close {
    position: absolute;
    top: 12px;
    right: 12px;
    display: inline-flex;
    width: 30px;
    height: 30px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-faint);
    cursor: pointer;
    transition: background-color var(--transition), color var(--transition);
  }
  .accepted-celebration-close:hover, .accepted-celebration-close:focus-visible { background: var(--color-bg-subtle); color: var(--color-text); }
  .accepted-celebration-close :deep(svg) { width: 17px; height: 17px; }
  .accepted-burst { position: relative; width: 150px; height: 136px; }
  .accepted-check {
    position: absolute;
    top: 26px;
    left: 37px;
    display: grid;
    width: 76px;
    height: 76px;
    place-items: center;
    border: 1px solid rgba(15, 123, 108, .2);
    border-radius: 50%;
    background: var(--tag-tools-bg);
    color: var(--cat-tools);
    box-shadow: 0 0 0 11px rgba(15, 123, 108, .055);
    animation: accepted-check-pop 520ms 100ms cubic-bezier(.2, .9, .22, 1.28) both;
  }
  .accepted-check :deep(svg) { width: 38px; height: 38px; stroke-width: 2.4; }
  .accepted-burst > span { position: absolute; display: block; width: 7px; height: 7px; border-radius: 2px; opacity: 0; animation: accepted-confetti 720ms 130ms ease-out both; }
  .accepted-burst .particle-1 { top: 18px; left: 18px; background: var(--cat-course); transform: rotate(18deg); }
  .accepted-burst .particle-2 { top: 4px; left: 59px; width: 5px; height: 12px; background: var(--cat-tools); transform: rotate(-12deg); }
  .accepted-burst .particle-3 { top: 15px; right: 21px; background: var(--cat-recommend); transform: rotate(40deg); }
  .accepted-burst .particle-4 { top: 50px; right: 2px; width: 5px; height: 12px; background: var(--color-link); transform: rotate(70deg); }
  .accepted-burst .particle-5 { right: 17px; bottom: 25px; background: var(--cat-competition); transform: rotate(-22deg); }
  .accepted-burst .particle-6 { right: 48px; bottom: 2px; width: 5px; height: 11px; background: var(--cat-course); transform: rotate(15deg); }
  .accepted-burst .particle-7 { bottom: 4px; left: 45px; background: var(--cat-tools); transform: rotate(42deg); }
  .accepted-burst .particle-8 { bottom: 27px; left: 11px; width: 5px; height: 12px; background: var(--cat-recommend); transform: rotate(-62deg); }
  .accepted-burst .particle-9 { top: 55px; left: 0; background: var(--color-link); transform: rotate(16deg); }
  .accepted-burst .particle-10 { top: 35px; left: 24px; width: 5px; height: 10px; background: var(--cat-competition); transform: rotate(-30deg); }
  .accepted-burst .particle-11 { top: 34px; right: 29px; background: var(--cat-course); transform: rotate(55deg); }
  .accepted-burst .particle-12 { right: 32px; bottom: 40px; width: 5px; height: 11px; background: var(--cat-tools); transform: rotate(-18deg); }
  .accepted-eyebrow { margin: 2px 0 5px; color: var(--cat-tools); font-size: 11px; font-weight: 750; letter-spacing: .14em; text-transform: uppercase; }
  .accepted-celebration-card > strong { color: var(--color-text); font-family: var(--font-serif); font-size: 34px; font-weight: 700; letter-spacing: -.035em; line-height: 1.1; }
  .accepted-problem-title { display: block; max-width: 260px; overflow: hidden; margin-top: 9px; color: var(--color-text-muted); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
  .accepted-celebration-enter-active, .accepted-celebration-leave-active { transition: opacity 220ms ease; }
  .accepted-celebration-enter-from, .accepted-celebration-leave-to { opacity: 0; }

  @keyframes accepted-card-pop {
    from { opacity: 0; transform: translateY(18px) scale(.88); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }
  @keyframes accepted-check-pop {
    from { opacity: 0; transform: scale(.35) rotate(-18deg); }
    to { opacity: 1; transform: scale(1) rotate(0); }
  }
  @keyframes accepted-confetti {
    0% { opacity: 0; scale: .35; }
    35% { opacity: 1; scale: 1; }
    100% { opacity: .78; translate: 0 7px; scale: .82; }
  }

  .card-title { margin-left: 0; }
  .info-heading { display: inline-flex; align-items: center; gap: 8px; }

  .problem-workspace {
    display: grid;
    width: 100%;
    align-items: start;
    grid-template-columns: minmax(0, 1.04fr) minmax(0, .96fr);
    gap: 12px;
  }

  #problem-main, #solution-column {
    min-width: 0;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-bg);
    box-shadow: var(--shadow-card);
  }

  #problem-main {
    :deep(.el-card) { overflow: visible; border: 0; border-radius: 0; box-shadow: none; }
    :deep(.el-card__header) {
      padding: 16px 22px;
      border-bottom: 1px solid var(--color-border);
      background: var(--color-bg);
    }
    :deep(.el-card__body) { padding: 18px 26px 34px !important; }
  }

  .problem-title-header { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 18px; }
  .problem-title-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 2px; }
  .problem-title-copy small { color: var(--color-text-faint); font-family: var(--font-mono); font-size: 10px; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; }
  .problem-title-line { display: flex; min-width: 0; align-items: flex-end; justify-content: space-between; gap: 16px; }
  .problem-title-copy strong { min-width: 0; flex: 1; overflow: hidden; color: var(--color-text); font-family: var(--font-serif); font-size: 23px; font-weight: 650; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
  .problem-title-tags { display: flex; width: fit-content; max-width: 48%; max-height: 51px; flex: none; align-items: flex-end; justify-content: flex-end; flex-wrap: wrap; gap: 5px; overflow: hidden; }
  .problem-title-tags span { display: inline-flex; max-width: 132px; min-height: 23px; align-items: center; overflow: hidden; padding: 0 8px; border: 1px solid var(--color-border); border-radius: var(--radius-pill); background: var(--color-bg-subtle); color: var(--color-text-muted); font-family: var(--font-sans); font-size: 11px; font-weight: 600; line-height: 1; text-overflow: ellipsis; white-space: nowrap; }
  .problem-header-action {
    display: inline-flex;
    min-height: 32px;
    flex: none;
    align-items: center;
    gap: 6px;
    padding: 0 9px;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-muted);
    font-family: var(--font-sans);
    font-size: 12px;
    cursor: pointer;
    transition: color var(--transition), border-color var(--transition), background-color var(--transition);
  }
  .problem-header-action:hover, .problem-header-action:focus-visible { border-color: var(--color-border); background: var(--color-bg-subtle); color: var(--color-text); }
  .problem-header-action :deep(.legacy-icon) { display: inline-flex; align-items: center; }

  .problem-brief {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(116px, 1fr));
    overflow: hidden;
    margin-bottom: 20px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background: #fcfbf9;
  }
  .problem-brief > div { display: flex; min-width: 0; min-height: 58px; justify-content: center; flex-direction: column; padding: 10px 13px; border-right: 1px solid var(--color-border); }
  .problem-brief > div:last-child { border-right: 0; }
  .problem-brief span { color: var(--color-text-faint); font-size: 10px; font-weight: 650; }
  .problem-brief strong { overflow: hidden; margin-top: 3px; color: var(--color-text); font-size: 12px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
  .problem-level-item { align-items: flex-start; }
  .problem-level-badge {
    display: inline-flex;
    min-width: 58px;
    min-height: 23px;
    align-items: center;
    justify-content: center;
    padding: 0 9px;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    line-height: 1;
  }
  .problem-level-badge.difficulty-low { border-color: color-mix(in srgb, var(--cat-tools) 20%, transparent); background: var(--tag-tools-bg); color: var(--cat-tools); }
  .problem-level-badge.difficulty-mid { border-color: color-mix(in srgb, var(--cat-kaggle) 20%, transparent); background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
  .problem-level-badge.difficulty-high { border-color: color-mix(in srgb, var(--cat-research) 20%, transparent); background: var(--tag-research-bg); color: var(--cat-research); }
  .problem-level-empty { color: var(--color-text-faint) !important; font-weight: 500 !important; }

  #submit-code { overflow: hidden; border-bottom: 1px solid var(--color-border); background: var(--color-bg); }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; margin: -1px; padding: 0; border: 0; clip: rect(0 0 0 0); white-space: nowrap; }
  #submit-code :deep(.code-editor-shell) { display: flex; min-height: 0; flex-direction: column; margin: 0; }
  #submit-code :deep(.editor-toolbar) { min-height: 50px; margin: 0; padding: 8px 12px; border-bottom: 1px solid var(--color-border); }
  #submit-code :deep(.toolbar-label) { font-size: 12px; }
  #submit-code :deep(.adjust) { width: 132px; }
  #submit-code :deep(.cm6-adapter .cm-editor) { min-height: clamp(400px, 54vh, 540px); max-height: none; border: 0; border-bottom: 1px solid var(--color-border); border-radius: 0; }
  #submit-code :deep(.cm-content) { padding-top: 13px; }
  #submit-code :deep(.cm-gutters) { min-width: 36px; }
  #submit-code :deep(.cm-lineNumbers .cm-gutterElement) { min-width: 34px; padding: 0 6px 0 2px; text-align: right; }

  .submit-dock { display: flex; min-height: 64px; align-items: center; justify-content: space-between; gap: 14px; padding: 10px 12px; background: var(--color-bg); }
  .submit-feedback { min-width: 0; flex: 1; }

  #problem-content {
    margin-top: 0;
    .title {
      font-size: 18px;
      font-weight: 600;
      margin: 26px 0 9px;
      color: var(--color-text);
      line-height: 27px;
      padding-bottom: 5px;
      border-bottom: 1px solid var(--color-border);
      .copy {
        display: inline-flex;
        width: 24px;
        height: 24px;
        align-items: center;
        justify-content: center;
        margin-left: 6px;
        border-radius: 4px;
        color: var(--color-link);
        vertical-align: middle;
        transition: color var(--transition), background-color var(--transition);
      }
      .copy:hover { background: rgba(35, 131, 226, .08); color: var(--color-link); }
      .copy:focus-visible { outline: 2px solid rgba(35, 131, 226, .32); outline-offset: 1px; color: var(--color-link); }
    }
    > .title:first-of-type { margin-top: 0; }
    :deep(code) {
      border-radius: 4px;
      background: rgba(135, 131, 120, .08);
      color: #d14848;
    }
    :deep(pre) {
      border-radius: var(--radius-sm);
      background: var(--color-bg);
    }
    :deep(pre code) {
      background: transparent;
      color: var(--color-text);
    }
    p.content { margin: 0 2px 15px; font-size: 14px; line-height: 1.75; }
    .sample { align-items: stretch; flex-direction: column; }
    .sample-input, .sample-output { width: 100%; flex: 1 1 auto; display: flex; flex-direction: column; margin: 0; }
    .sample-output .title { margin-top: 15px; }
    .sample pre { flex: 1 1 auto; align-self: stretch; min-height: 76px; margin: 0; border: 1px solid var(--color-border); background: var(--color-bg); }
  }

  #submit-code {
    .status {
      display: flex;
      min-height: 36px;
      align-items: center;
      gap: 10px;
      > span { color: var(--color-text-muted); font-size: 13px; font-weight: 600; }
    }
    .submit-controls { display: flex; flex: none; align-items: center; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }
    .captcha-container { display: flex; align-items: center; gap: 8px; }
    .captcha-container img { display: block; width: 96px; height: 36px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); cursor: pointer; }
    .captcha-code { width: 120px; }
    .oj-submit-button { min-width: 126px; min-height: 38px; border-radius: var(--radius-sm); gap: 7px; font-weight: 650; }
    :deep(.oj-submit-button > span) { display: inline-flex; align-items: center; justify-content: center; gap: 10px; white-space: nowrap; }
    :deep(.oj-submit-button .legacy-icon) { display: inline-flex; flex: none; align-items: center; }
    .oj-submit-button.is-success { background: var(--oj-success); border-color: var(--oj-success); color: #fff; }
    .oj-submit-button.is-loading { cursor: wait; }
    .submit-spinner { animation: oj-submit-spin 900ms linear infinite; }
    @keyframes oj-submit-spin { to { transform: rotate(360deg); } }
  }

  .recent-submission-card {
    overflow: hidden;
    margin: 0;
    border: 0;
    border-bottom: 1px solid var(--color-border);
    border-radius: 0;
    background: var(--color-bg);
    box-shadow: none;
  }
  .recent-submission-header {
    display: flex;
    width: 100%;
    min-height: 48px;
    align-items: center;
    justify-content: space-between;
    padding: 10px 15px;
    border: 0;
    background: var(--color-bg);
    color: var(--color-text-muted);
    text-align: left;
    cursor: pointer;
    transition: color var(--transition), background-color var(--transition);
  }
  .recent-submission-header:hover, .recent-submission-header:focus-visible { background: var(--color-bg); color: var(--color-text); }
  .recent-submission-heading { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; }
  .recent-submission-heading :deep(.legacy-icon) { display: inline-flex; align-items: center; }
  .recent-submission-arrow { color: var(--color-text-faint); transform: rotate(-90deg); }
  .recent-submission-divider { width: 34px; height: 1px; margin: 0 16px 4px; background: var(--line-strong); }
  .recent-submission-list { padding: 2px 15px 8px; }
  .recent-submission-row { display: grid; min-width: 0; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 9px; padding: 8px 0; border-bottom: 1px solid var(--color-border); }
  .recent-submission-row:last-child { border-bottom: 0; }
  .recent-submission-main { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 1px; }
  .recent-submission-main strong { overflow: hidden; color: var(--color-text); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
  .recent-submission-main small, .recent-submission-row time { color: var(--color-text-muted); font-size: 11px; white-space: nowrap; }
  .recent-submission-row time { flex: none; color: var(--color-text-faint); }
  .recent-submission-empty { padding: 14px 0 10px; color: var(--color-text-faint); font-size: 12px; }

  .judge-status-badge {
    position: relative;
    display: inline-flex;
    overflow: hidden;
    width: fit-content;
    min-width: 72px;
    height: 24px;
    align-items: center;
    justify-content: center;
    padding: 0 9px;
    border: 0;
    border-radius: var(--radius-pill);
    font-size: 12px;
    font-weight: 650;
    line-height: 1;
    white-space: nowrap;
  }
  .judge-status-badge.is-success { --judge-status-bg: var(--tag-tools-bg); color: var(--cat-tools); background: var(--judge-status-bg); }
  .judge-status-badge.is-error { --judge-status-bg: var(--tag-research-bg); color: var(--cat-research); background: var(--judge-status-bg); }
  .judge-status-badge.is-warning { --judge-status-bg: var(--tag-course-bg); color: var(--cat-course); background: var(--judge-status-bg); }
  .judge-status-badge.is-info { --judge-status-bg: var(--tag-kaggle-bg); color: var(--cat-kaggle); background: var(--judge-status-bg); }
  .judge-status-badge:not(.is-success) {
    background-image:
      linear-gradient(108deg, transparent 28%, rgba(255, 255, 255, .72) 46%, transparent 64%),
      linear-gradient(var(--judge-status-bg), var(--judge-status-bg));
    background-position: 170% 0, 0 0;
    background-size: 190% 100%, 100% 100%;
    animation:
      judge-status-shimmer 1.65s linear infinite,
      judge-status-heartbeat 2.2s ease-in-out infinite;
    will-change: background-position, box-shadow;
  }
  .submission-status-link {
    cursor: pointer;
    transition: filter var(--transition), box-shadow var(--transition);
  }
  .submission-status-link:hover { filter: saturate(1.08) brightness(.98); }
  .submission-status-link:focus-visible { outline: 2px solid var(--color-focus-ring); outline-offset: 2px; }

  @keyframes judge-status-shimmer {
    from { background-position: 170% 0, 0 0; }
    to { background-position: -90% 0, 0 0; }
  }

  @keyframes judge-status-heartbeat {
    0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 0%, transparent); }
    45% { box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 8%, transparent); }
    55% { box-shadow: 0 0 0 1px color-mix(in srgb, currentColor 4%, transparent); }
  }

  #solution-column > :deep(.el-card) { margin: 0; border-right: 0; border-left: 0; border-radius: 0; box-shadow: none; }

  @media (max-width: 760px) { #submit-code .submit-controls { justify-content: stretch; } #submit-code .oj-submit-button { flex: 1 1 100%; } #submit-code .captcha-container { flex: 1 1 100%; } #submit-code .captcha-code { flex: 1; width: auto; } }

  @media (max-width: 1050px) {
    .problem-workspace { grid-template-columns: 1fr; }
    #submit-code :deep(.cm6-adapter .cm-editor) { min-height: 430px; }
    .recent-submission-card { width: 100%; }
  }

  @media (max-width: 620px) {
    #problem-main :deep(.el-card__header) { padding: 14px 16px; }
    #problem-main :deep(.el-card__body) { padding: 15px 16px 26px !important; }
    .problem-title-copy strong { font-size: 20px; }
    .problem-title-line { gap: 9px; }
    .problem-title-tags { max-width: 46%; gap: 4px; }
    .problem-title-tags span { max-width: 96px; min-height: 21px; padding: 0 6px; font-size: 10px; }
    .problem-header-action span { display: none; }
    .problem-brief { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .problem-brief > div { border-bottom: 1px solid var(--color-border); }
    .problem-brief > div:nth-child(2n) { border-right: 0; }
    .problem-brief > div:last-child { border-bottom: 0; }
    #submit-code :deep(.editor-toolbar) { align-items: flex-start; flex-direction: column; }
    #submit-code :deep(.editor-toolbar-group) { width: 100%; }
    #submit-code :deep(.theme-control .adjust) { flex: 1; width: auto; }
    #submit-code :deep(.cm6-adapter .cm-editor) { min-height: 360px; }
    .submit-dock { align-items: stretch; flex-direction: column; }
    #submit-code .submit-controls { width: 100%; justify-content: stretch; }
    #submit-code .oj-submit-button { flex: 1; }
    .recent-submission-row { grid-template-columns: minmax(0, 1fr) auto; }
    .recent-submission-row time { display: none; }
  }

  @media (prefers-reduced-motion: reduce) {
    .accepted-celebration-card, .accepted-check, .accepted-burst > span { animation: none; }
    .judge-status-badge:not(.is-success) { animation: none; }
    .accepted-celebration-enter-active, .accepted-celebration-leave-active { transition-duration: 80ms; }
  }
</style>
