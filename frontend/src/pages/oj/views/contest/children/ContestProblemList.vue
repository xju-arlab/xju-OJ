<template>
  <section class="contest-problem-panel" aria-labelledby="contest-problem-title">
    <header class="problem-panel-header">
      <div>
        <p>{{$t('m.Problems')}}</p>
        <h2 id="contest-problem-title">{{$t('m.Problems_List')}}</h2>
      </div>
      <span class="problem-count">{{problems.length}}</span>
    </header>

    <div class="problem-list-stage">
      <div :class="['problem-list-content', { 'is-registration-locked': registrationRequired }]">
        <div v-if="problems.length" class="problem-table-wrap">
          <table class="contest-problem-table">
            <thead>
              <tr>
                <th class="problem-id">#</th>
                <th>{{$t('m.Title')}}</th>
                <th v-if="showStatistics" class="numeric">{{$t('m.Total')}}</th>
                <th v-if="showStatistics" class="numeric">{{$t('m.AC_Rate')}}</th>
                <th v-if="showUserStatus" class="problem-status">{{$t('m.Status')}}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(problem, index) in problems"
                  :key="problem._id"
                  tabindex="0"
                  @click="goContestProblem(problem)"
                  @keydown.enter.prevent="goContestProblem(problem)">
                <td class="problem-id"><span>{{problemLabel(problem, index)}}</span></td>
                <td>
                  <router-link class="problem-title-link" :to="problemRoute(problem)" @click.stop>
                    <strong>{{problem.title}}</strong>
                    <Icon type="arrow-down-b" />
                  </router-link>
                </td>
                <td v-if="showStatistics" class="numeric">{{problem.submission_number || 0}}</td>
                <td v-if="showStatistics" class="numeric">{{getACRate(problem.accepted_number, problem.submission_number)}}</td>
                <td v-if="showUserStatus" class="problem-status">
                  <span v-if="problem.my_status === 0" class="attempt-status is-accepted">
                    <Icon type="check" />{{$t('m.Accepted')}}
                  </span>
                  <span v-else-if="problem.my_status !== null && problem.my_status !== undefined" class="attempt-status is-attempted">
                    <Icon type="refresh" />{{$t('m.Submissions')}}
                  </span>
                  <span v-else class="attempt-status is-empty">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else class="problem-empty">
          <Icon type="ios-photos" />
          <p>{{$t('m.No_Problems')}}</p>
        </div>
      </div>

      <div v-if="registrationRequired" class="contest-registration-gate">
        <span class="registration-gate-icon" aria-hidden="true"><Icon type="trophy" /></span>
        <strong>{{$t('m.Contest_Registration_Required')}}</strong>
        <p>{{$t('m.Contest_Registration_Description')}}</p>
        <LegacyButton type="primary" @click="openRegistration">
          {{$t('m.Register_For_Contest')}}
        </LegacyButton>
      </div>
    </div>

    <Modal v-model="registrationModalVisible"
           :width="430"
           :mask-closable="!registering"
           :closable="!registering">
      <template #header>
        <div class="registration-modal-title">{{$t('m.Confirm_Contest_Registration')}}</div>
      </template>
      <div class="registration-modal-body">
        <p>{{$t('m.Confirm_Contest_Registration_Description')}}</p>
        <Input v-if="requiresPassword"
               v-model="contestPassword"
               type="password"
               :placeholder="$t('m.Contest_Password')"
               @on-enter="confirmRegistration" />
      </div>
      <template #footer>
        <div class="registration-modal-actions">
          <LegacyButton :disabled="registering" @click="registrationModalVisible = false">
            {{$t('m.Cancel')}}
          </LegacyButton>
          <LegacyButton type="primary" :loading="registering" @click="confirmRegistration">
            {{$t('m.Confirm_Registration')}}
          </LegacyButton>
        </div>
      </template>
    </Modal>
  </section>
</template>

<script>
  import { mapActions, mapState, mapGetters } from '@/store/compat'
  import utils from '@/utils/utils'
  import { CONTEST_STATUS, CONTEST_TYPE } from '@/utils/constants'

  export default {
    name: 'ContestProblemList',
    data () {
      return {
        registrationModalVisible: false,
        registering: false,
        contestPassword: ''
      }
    },
    mounted () {
      this.getContestProblems().catch(() => {})
    },
    methods: {
      ...mapActions(['changeModalStatus', 'getContestProblems', 'registerContest']),
      getACRate (accepted, total) {
        return utils.getACRate(accepted, total)
      },
      problemLabel (problem, index) {
        return problem._id || String.fromCharCode(65 + index)
      },
      problemRoute (problem) {
        return {
          name: 'contest-problem-details',
          params: {
            contestID: this.$route.params.contestID,
            problemID: problem._id
          }
        }
      },
      goContestProblem (problem) {
        if (this.registrationRequired) {
          this.openRegistration()
          return
        }
        this.$router.push(this.problemRoute(problem))
      },
      openRegistration () {
        if (!this.isAuthenticated) {
          this.changeModalStatus({ mode: 'login', visible: true })
          return
        }
        this.registrationModalVisible = true
      },
      confirmRegistration () {
        if (this.registering) return
        if (this.requiresPassword && !this.contestPassword) {
          this.$error(this.$t('m.Contest_Password_Required'))
          return
        }
        this.registering = true
        this.registerContest({ password: this.contestPassword }).then(() => {
          this.registrationModalVisible = false
          this.contestPassword = ''
          this.$success(this.$t('m.Contest_Registration_Succeeded'))
          return this.getContestProblems()
        }).finally(() => {
          this.registering = false
        })
      }
    },
    computed: {
      ...mapState({
        contest: state => state.contest.contest,
        problems: state => state.contest.contestProblems
      }),
      ...mapGetters([
        'isAuthenticated', 'isContestAdmin', 'isContestRegistered',
        'contestRuleType', 'contestStatus', 'OIContestRealTimePermission'
      ]),
      registrationRequired () {
        return !this.isContestAdmin &&
          this.contestStatus !== CONTEST_STATUS.ENDED &&
          !this.isContestRegistered
      },
      requiresPassword () {
        return this.contest.contest_type === CONTEST_TYPE.PRIVATE
      },
      showStatistics () {
        return this.contestRuleType === 'ACM' || this.OIContestRealTimePermission
      },
      showUserStatus () {
        return this.isAuthenticated && this.problems.some(problem => problem.my_status !== null && problem.my_status !== undefined)
      }
    }
  }
</script>

<style scoped lang="less">
@import "@/styles/contest-problems.less";
</style>
