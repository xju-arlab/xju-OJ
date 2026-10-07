<template>
  <div class="contest-editor">
    <Panel :title="title">
      <el-form class="contest-form" label-position="top">
        <section class="form-section">
          <div class="section-heading">
            <div>
              <h3>基本信息</h3>
              <p>设置比赛名称、开放时间和访问凭据。</p>
            </div>
          </div>

          <div class="field-grid identity-grid">
            <el-form-item :label="$t('m.ContestTitle')" required>
              <el-input v-model="contest.title" :placeholder="$t('m.ContestTitle')"></el-input>
            </el-form-item>
            <el-form-item :label="$t('m.Contest_Password')">
              <el-input
                v-model="contest.password"
                clearable
                show-password
                placeholder="不填写则无需密码">
              </el-input>
            </el-form-item>
          </div>

          <div class="field-grid time-grid">
            <el-form-item :label="$t('m.Contest_Start_Time')" required>
              <el-date-picker
                v-model="contest.start_time"
                class="full-control"
                type="datetime"
                :placeholder="$t('m.Contest_Start_Time')">
              </el-date-picker>
            </el-form-item>
            <el-form-item :label="$t('m.Contest_End_Time')" required>
              <el-date-picker
                v-model="contest.end_time"
                class="full-control"
                type="datetime"
                :placeholder="$t('m.Contest_End_Time')">
              </el-date-picker>
            </el-form-item>
          </div>
        </section>

        <section class="form-section">
          <div class="section-heading">
            <div>
              <h3>比赛设置</h3>
              <p>确定计分规则、排名更新方式和比赛可见状态。</p>
            </div>
          </div>

          <div class="setting-grid">
            <div class="setting-card">
              <span class="setting-copy">
                <strong>{{ $t('m.Contest_Rule_Type') }}</strong>
                <small>创建后不可更改</small>
              </span>
              <el-select v-model="contest.rule_type" class="rule-select" :disabled="disableRuleType">
                <el-option label="ACM" value="ACM"></el-option>
                <el-option label="OI" value="OI"></el-option>
                <el-option label="AI" value="AI"></el-option>
              </el-select>
            </div>
            <div class="setting-card">
              <span class="setting-copy">
                <strong>{{ $t('m.Real_Time_Rank') }}</strong>
                <small>比赛期间实时更新排名</small>
              </span>
              <el-switch v-model="contest.real_time_rank"></el-switch>
            </div>
            <div class="setting-card">
              <span class="setting-copy">
                <strong>{{ $t('m.Contest_Status') }}</strong>
                <small>允许用户看到并进入比赛</small>
              </span>
              <el-switch v-model="contest.visible"></el-switch>
            </div>
          </div>
        </section>

        <section class="form-section description-section">
          <div class="section-heading">
            <div>
              <h3>{{ $t('m.ContestDescription') }}</h3>
              <p>填写比赛说明、规则补充和其他参赛须知。</p>
            </div>
          </div>
          <Simditor v-model="contest.description"></Simditor>
        </section>

        <ContestProblemComposer
          v-if="isCreate && contest.rule_type !== 'AI'"
          ref="problemComposer"
          v-model="problemPlan"
          :rule-type="contest.rule_type" />
        <AIContestSettings v-if="contest.rule_type === 'AI'" ref="aiSettings" :contest-id="isCreate ? '' : $route.params.contestId" />

        <div class="form-actions">
          <save :disabled="saving" @click="saveContest"></save>
        </div>
      </el-form>
    </Panel>
  </div>
</template>

<script>
  import api from '../../api.js'
  import Simditor from '../../components/Simditor.vue'
  import ContestProblemComposer from './ContestProblemComposer.vue'
  import AIContestSettings from '../ai/ContestSettings.vue'

  export default {
    name: 'CreateContest',
    components: {
      Simditor,
      ContestProblemComposer,
      AIContestSettings
    },
    data () {
      return {
        title: '创建比赛',
        disableRuleType: false,
        problemPlan: [],
        saving: false,
        contest: {
          title: '',
          description: '',
          start_time: '',
          end_time: '',
          rule_type: 'ACM',
          password: '',
          real_time_rank: true,
          visible: true,
          allowed_ip_ranges: []
        }
      }
    },
    computed: {
      isCreate () {
        return this.$route.name !== 'edit-contest'
      }
    },
    methods: {
      async saveContest () {
        if (this.saving) return
        const incompatibleProblem = this.problemPlan.find(item => (
          (item.kind === 'REMOTE' && this.contest.rule_type !== 'ACM') ||
          (item.kind === 'PUBLIC' && item.ruleType && item.ruleType !== this.contest.rule_type)
        ))
        if (incompatibleProblem && this.contest.rule_type !== 'AI') {
          this.$error('题目编排中存在与当前比赛规则不兼容的题目，请先删除或切回对应规则')
          return
        }
        this.saving = true
        let funcName = this.$route.name === 'edit-contest' ? 'editContest' : 'createContest'
        let data = Object.assign({}, this.contest)
        data.allowed_ip_ranges = Array.isArray(data.allowed_ip_ranges) ? data.allowed_ip_ranges : []
        try {
          if (this.contest.rule_type === 'AI') this.$refs.aiSettings.validate()
          const res = await api[funcName](data)
          const contestId = (res.data.data || {}).id
          if (this.contest.rule_type === 'AI') {
            try { await this.$refs.aiSettings.save(contestId) } catch (error) {
              this.$error(`比赛已保存，AI 评测设置保存失败：${error.message}`)
              if (this.isCreate) this.$router.replace({ name: 'edit-contest', params: { contestId } })
              return
            }
          }
          if (this.isCreate && this.contest.rule_type !== 'AI' && this.problemPlan.length) {
            try {
              await this.$refs.problemComposer.materialize(contestId)
            } catch (error) {
              this.$error(`比赛已创建，但题目编排未全部完成：${error.message || '导入失败'}`)
              this.$router.push({name: 'contest-problem-list', params: {contestId}})
              return
            }
          }
          this.$router.push({name: 'contest-list', query: {refresh: 'true'}})
        } catch (error) {
          this.$error(error.message || '比赛保存失败')
        } finally {
          this.saving = false
        }
      }
    },
    mounted () {
      if (this.$route.name === 'edit-contest') {
        this.title = '编辑比赛'
        this.disableRuleType = true
        api.getContest(this.$route.params.contestId).then(res => {
          this.contest = res.data.data
        }).catch(() => {
        })
      }
    }
  }
</script>

<style scoped lang="less">
  .contest-editor { --form-gap: 18px; }
  .contest-form { display: grid; gap: 18px; }
  .form-section { padding: 20px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg); }
  .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
  .section-heading h3 { margin: 0; color: var(--color-text); font-size: 16px; font-weight: 680; }
  .section-heading p { margin: 4px 0 0; color: var(--color-text-muted); font-size: 12px; line-height: 1.55; }
  .field-grid { display: grid; gap: 0 var(--form-gap); }
  .identity-grid { grid-template-columns: minmax(0, 3fr) minmax(220px, 1fr); }
  .time-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .full-control { width: 100%; }
  .setting-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .setting-card { display: flex; min-height: 66px; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 14px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg-subtle); }
  .setting-copy, .setting-copy strong, .setting-copy small { display: block; }
  .setting-copy { min-width: 0; flex: 1; }
  .setting-copy strong { color: var(--color-text); font-size: 13px; }
  .setting-copy small { margin-top: 3px; color: var(--color-text-muted); font-size: 11px; white-space: nowrap; }
  .form-actions { display: flex; justify-content: flex-end; padding: 2px 0 6px; }

  :deep(.el-form-item) { min-width: 0; }
  :deep(.el-form-item__label) { color: var(--color-text-muted); font-size: 12px; font-weight: 620; }
  :deep(.el-input), :deep(.el-select), :deep(.el-date-editor) { width: 100%; }
  :deep(.setting-card .el-select.rule-select) { width: 108px; flex: none; }

  @media (max-width: 1000px) {
    .setting-grid { grid-template-columns: 1fr; }
  }

  @media (max-width: 760px) {
    .form-section { padding: 15px; }
    .identity-grid, .time-grid { grid-template-columns: 1fr; }
    .section-heading { align-items: flex-start; }
    .setting-card { min-height: 62px; }
  }
</style>
