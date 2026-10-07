<template>
  <div class="problem">
    <Panel :title="title">
      <el-alert v-if="problem.judge_mode === 'REMOTE'"
                class="remote-alert"
                type="warning"
                :closable="false"
                :title="`远程题目 · ${remoteProviderLabel(problem.remote_oj)} / ${problem.remote_problem_id}`"
                description="远程题目无需上传本地测试数据，提交将由对应来源平台评测。">
      </el-alert>

      <el-form ref="form" class="problem-form" :model="problem" :rules="rules" label-position="top">
        <section class="form-section">
          <div class="section-heading">
            <div>
              <h3>基本信息</h3>
              <p>题号由系统自动分配，只需维护标题、来源与判题属性。</p>
            </div>
          </div>

          <div class="field-grid basic-grid">
            <el-form-item class="title-field" prop="title" :label="$t('m.Title')" required>
              <el-input :placeholder="$t('m.Title')" v-model="problem.title"></el-input>
            </el-form-item>
            <el-form-item label="来源">
              <el-select v-model="problem.source" class="full-control" placeholder="请选择来源">
                <el-option v-for="option in sourceOptions"
                           :key="option.value"
                           :label="option.label"
                           :value="option.value"></el-option>
              </el-select>
            </el-form-item>
          </div>

          <div class="field-grid limit-grid">
            <el-form-item :label="$t('m.Time_Limit') + ' (ms)'" required>
              <el-input type="number" :placeholder="$t('m.Time_Limit')" v-model="problem.time_limit"></el-input>
            </el-form-item>
            <el-form-item :label="$t('m.Memory_limit') + ' (MB)'" required>
              <el-input type="number" :placeholder="$t('m.Memory_limit')" v-model="problem.memory_limit"></el-input>
            </el-form-item>
            <el-form-item :label="$t('m.Difficulty')">
              <el-select class="full-control" :placeholder="$t('m.Difficulty')" v-model="problem.difficulty">
                <el-option :label="$t('m.Low')" value="Low"></el-option>
                <el-option :label="$t('m.Mid')" value="Mid"></el-option>
                <el-option :label="$t('m.High')" value="High"></el-option>
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('m.Type')">
              <el-select class="full-control" v-model="problem.rule_type" :disabled="disableRuleType">
                <el-option label="ACM" value="ACM"></el-option>
                <el-option label="OI" value="OI"></el-option>
              </el-select>
            </el-form-item>
          </div>

          <div class="field-grid metadata-grid">
            <el-form-item :label="$t('m.Tag')" :error="error.tags" required>
              <div class="tag-editor">
                <span class="tags">
                  <el-tag v-for="tag in problem.tags"
                          :key="tag"
                          :closable="true"
                          :close-transition="false"
                          type="success"
                          @close="closeTag(tag)">{{tag}}</el-tag>
                </span>
                <el-autocomplete v-if="inputVisible"
                                 size="small"
                                 class="input-new-tag"
                                 popper-class="problem-tag-poper"
                                 v-model="tagInput"
                                 :trigger-on-focus="false"
                                 :fetch-suggestions="querySearch"
                                 @keyup.enter="addTag"
                                 @select="addTag"></el-autocomplete>
                <el-button v-else class="button-new-tag" size="small" @click="inputVisible = true">
                  + {{$t('m.New_Tag')}}
                </el-button>
              </div>
            </el-form-item>
            <el-form-item :label="$t('m.Languages')" :error="error.languages" required>
              <el-checkbox-group v-model="problem.languages" class="language-options">
                <el-tooltip v-for="lang in allLanguage.languages"
                            :key="lang.name"
                            effect="dark"
                            :content="lang.description"
                            placement="top-start">
                  <el-checkbox :label="lang.name"></el-checkbox>
                </el-tooltip>
              </el-checkbox-group>
            </el-form-item>
          </div>

          <div class="toggle-row">
            <label class="toggle-field">
              <span><strong>{{$t('m.Visible')}}</strong><small>允许普通用户在题库中看到该题</small></span>
              <el-switch v-model="problem.visible"></el-switch>
            </label>
            <label class="toggle-field">
              <span><strong>{{$t('m.ShareSubmission')}}</strong><small>允许其他用户查看共享提交</small></span>
              <el-switch v-model="problem.share_submission"></el-switch>
            </label>
          </div>
        </section>

        <section class="form-section">
          <div class="section-heading">
            <div>
              <h3>题面内容</h3>
              <p>原文模式用于直接编辑 Markdown，预览模式可在渲染后的富文本中继续编辑。</p>
            </div>
          </div>

          <el-form-item prop="description" :label="$t('m.Description')" required>
            <Simditor v-model="problem.description"></Simditor>
          </el-form-item>
          <div class="field-grid statement-grid">
            <el-form-item prop="input_description" :label="$t('m.Input_Description')" required>
              <Simditor v-model="problem.input_description"></Simditor>
            </el-form-item>
            <el-form-item prop="output_description" :label="$t('m.Output_Description')" required>
              <Simditor v-model="problem.output_description"></Simditor>
            </el-form-item>
          </div>
          <el-form-item :label="$t('m.Hint')">
            <Simditor v-model="problem.hint"></Simditor>
          </el-form-item>
        </section>

        <section class="form-section">
          <div class="section-heading is-inline">
            <div>
              <h3>样例</h3>
              <p>样例按题面展示顺序排列。</p>
            </div>
            <el-button type="primary" size="small" @click="addSample">
              <Icon type="plus" />{{$t('m.Add_Sample')}}
            </el-button>
          </div>

          <div class="sample-list">
            <article v-for="(sample, index) in problem.samples" :key="'sample' + index" class="sample-card">
              <div class="sample-card-heading">
                <strong>样例 {{ index + 1 }}</strong>
                <icon-btn danger name="删除样例" icon="trash" @click="deleteSample(index)"></icon-btn>
              </div>
              <div class="field-grid sample-grid">
                <el-form-item :label="$t('m.Input_Samples')" required>
                  <el-input :rows="6" type="textarea" :placeholder="$t('m.Input_Samples')" v-model="sample.input"></el-input>
                </el-form-item>
                <el-form-item :label="$t('m.Output_Samples')" required>
                  <el-input :rows="6" type="textarea" :placeholder="$t('m.Output_Samples')" v-model="sample.output"></el-input>
                </el-form-item>
              </div>
            </article>
          </div>
        </section>

        <section class="form-section judge-section">
          <div class="section-heading is-inline">
            <div>
              <h3>判题设置</h3>
              <p>{{ problem.judge_mode === 'REMOTE' ? '远程题目使用来源平台的测试数据。' : '配置本地测试数据、输入输出模式与特殊判题。' }}</p>
            </div>
            <el-upload v-if="problem.judge_mode !== 'REMOTE'"
                       :headers="csrfHeaders()"
                       action="/api/admin/test_case"
                       name="file"
                       :data="{spj: problem.spj}"
                       :show-file-list="true"
                       :on-success="uploadSucceeded"
                       :on-error="uploadFailed">
              <el-button size="small" type="primary"><Icon type="upload" />上传测试数据</el-button>
            </el-upload>
          </div>

          <template v-if="problem.judge_mode !== 'REMOTE'">
            <div class="field-grid judge-grid">
              <el-form-item :label="$t('m.IOMode')">
                <el-select class="full-control" v-model="problem.io_mode.io_mode">
                  <el-option label="标准输入输出" value="Standard IO"></el-option>
                  <el-option label="文件输入输出" value="File IO"></el-option>
                </el-select>
              </el-form-item>
              <el-form-item v-if="problem.io_mode.io_mode === 'File IO'" :label="$t('m.InputFileName')" required>
                <el-input v-model="problem.io_mode.input"></el-input>
              </el-form-item>
              <el-form-item v-if="problem.io_mode.io_mode === 'File IO'" :label="$t('m.OutputFileName')" required>
                <el-input v-model="problem.io_mode.output"></el-input>
              </el-form-item>
              <el-form-item :label="$t('m.Special_Judge')" :error="error.spj">
                <el-checkbox v-model="problem.spj" @click.prevent="switchSpj()">{{$t('m.Use_Special_Judge')}}</el-checkbox>
              </el-form-item>
            </div>

            <div v-if="problem.spj" class="spj-editor-card">
              <div class="subsection-heading">
                <strong>{{$t('m.Special_Judge_Code')}}</strong>
                <div class="subsection-actions">
                  <el-select v-model="problem.spj_language" size="small" class="spj-language-select">
                    <el-option v-for="lang in allLanguage.spj_languages"
                               :key="lang.name"
                               :label="lang.name"
                               :value="lang.name"></el-option>
                  </el-select>
                  <el-button type="primary" size="small" @click="compileSPJ" :loading="loadingCompile">
                    <Icon type="shuffle" />{{$t('m.Compile')}}
                  </el-button>
                </div>
              </div>
              <code-mirror v-model="problem.spj_code" :mode="spjMode"></code-mirror>
            </div>

            <el-alert v-if="error.testCase" class="testcase-error" type="error" :closable="false" :title="error.testCase"></el-alert>
            <el-table v-if="problem.test_case_score && problem.test_case_score.length" :data="problem.test_case_score" class="testcase-table">
              <el-table-column prop="input_name" :label="$t('m.Input')"></el-table-column>
              <el-table-column prop="output_name" :label="$t('m.Output')"></el-table-column>
              <el-table-column prop="score" :label="$t('m.Score')">
                <template #default="scope">
                  <el-input size="small"
                            :placeholder="$t('m.Score')"
                            v-model="scope.row.score"
                            :disabled="problem.rule_type !== 'OI'"></el-input>
                </template>
              </el-table-column>
            </el-table>
          </template>
        </section>

        <div class="form-actions">
          <save @click="submit()">保存题目</save>
        </div>
      </el-form>
    </Panel>
  </div>
</template>
<script>
  import { h } from 'vue'
  import { csrfHeaders } from '@/utils/csrf'
  import { apiErrorMessage } from '@/utils/apiError'
  import Simditor from '../../components/Simditor'
  import CodeMirror from '../../components/CodeMirror'
  import api from '../../api'

  export default {
    name: 'Problem',
    components: {
      Simditor,
      CodeMirror
    },
    data () {
      return {
        rules: {
          title: {required: true, message: '请输入题目标题', trigger: 'blur'},
          input_description: {required: true, message: '请输入输入描述', trigger: 'blur'},
          output_description: {required: true, message: '请输入输出描述', trigger: 'blur'}
        },
        loadingCompile: false,
        compiledSpj: null,
        mode: '',
        contest: {},
        problem: {
          languages: [],
          io_mode: {'io_mode': 'Standard IO', 'input': 'input.txt', 'output': 'output.txt'}
        },
        reProblem: {
          languages: [],
          io_mode: {'io_mode': 'Standard IO', 'input': 'input.txt', 'output': 'output.txt'}
        },
        testCaseUploaded: false,
        allLanguage: {},
        inputVisible: false,
        tagInput: '',
        sourceOptions: [
          { label: 'XJU-OJ', value: 'XJU-OJ' },
          { label: '牛客', value: '牛客' },
          { label: '洛谷', value: '洛谷' },
          { label: 'Codeforces', value: 'Codeforces' }
        ],
        title: '',
        spjMode: '',
        disableRuleType: false,
        routeName: '',
        error: {
          tags: '',
          spj: '',
          languages: '',
          testCase: ''
        }
      }
    },
    mounted () {
      this.routeName = this.$route.name
      if (this.routeName === 'edit-problem' || this.routeName === 'edit-contest-problem') {
        this.mode = 'edit'
      } else {
        this.mode = 'add'
      }
      api.getLanguages().then(res => {
        this.problem = {
          title: '',
          description: '',
          input_description: '',
          output_description: '',
          time_limit: 1000,
          memory_limit: 256,
          difficulty: 'Low',
          visible: true,
          share_submission: false,
          tags: [],
          languages: [],
          template: {},
          samples: [{input: '', output: ''}],
          spj: false,
          spj_language: '',
          spj_code: '',
          spj_compile_ok: false,
          test_case_id: '',
          test_case_score: [],
          rule_type: 'ACM',
          hint: '',
          source: 'XJU-OJ',
          judge_mode: 'LOCAL',
          remote_oj: null,
          remote_problem_id: null,
          remote_problem_data: {},
          io_mode: {'io_mode': 'Standard IO', 'input': 'input.txt', 'output': 'output.txt'}
        }
        let contestID = this.$route.params.contestId
        if (contestID) {
          this.problem.contest_id = this.reProblem.contest_id = contestID
          this.disableRuleType = true
          api.getContest(contestID).then(res => {
            this.problem.rule_type = this.reProblem.rule_type = res.data.data.rule_type
            this.contest = res.data.data
          })
        }

        this.problem.spj_language = 'C'

        let allLanguage = res.data.data
        this.allLanguage = allLanguage

        // get problem after getting languages list to avoid find undefined value in `watch problem.languages`
        if (this.mode === 'edit') {
          this.title = this.$t('m.Edit_Problem')
          let funcName = {'edit-problem': 'getProblem', 'edit-contest-problem': 'getContestProblem'}[this.routeName]
          api[funcName](this.$route.params.problemId).then(problemRes => {
            let data = problemRes.data.data
            if (!data.spj_code) {
              data.spj_code = ''
            }
            data.spj_language = data.spj_language || 'C'
            data.source = this.normalizedSource(data)
            this.compiledSpj = {code: data.spj_code, language: data.spj_language}
            this.problem = data
            this.testCaseUploaded = data.judge_mode === 'REMOTE' || Boolean(data.test_case_id)
            if (data.judge_mode === 'REMOTE') {
              this.disableRuleType = true
            }
          })
        } else {
          this.title = this.$t('m.Add_Problem')
          for (let item of allLanguage.languages) {
            this.problem.languages.push(item.name)
          }
        }
      })
    },
    watch: {
      'problem.spj_code' () {
        if (this.compiledSpj && this.problem.spj_code !== this.compiledSpj.code) this.problem.spj_compile_ok = false
      },
      'problem.spj_language' (newVal) {
        if (this.compiledSpj && newVal !== this.compiledSpj.language) this.problem.spj_compile_ok = false
        const language = (this.allLanguage.spj_languages || []).find(item => {
          return item.name === this.problem.spj_language
        })
        this.spjMode = language ? language.content_type : ''
      }
    },
    methods: {
      csrfHeaders,
      remoteProviderLabel (provider) {
        return {
          NOWCODER: '牛客',
          LUOGU: '洛谷',
          CODEFORCES: 'Codeforces'
        }[provider] || provider
      },
      normalizedSource (problem) {
        const remoteSources = {
          NOWCODER: '牛客',
          LUOGU: '洛谷',
          CODEFORCES: 'Codeforces'
        }
        if (problem.remote_oj && remoteSources[problem.remote_oj]) return remoteSources[problem.remote_oj]
        const source = String(problem.source || '')
        if (/牛客|nowcoder/i.test(source)) return '牛客'
        if (/洛谷|luogu/i.test(source)) return '洛谷'
        if (/codeforces/i.test(source)) return 'Codeforces'
        return 'XJU-OJ'
      },
      switchSpj () {
        if (this.testCaseUploaded) {
          this.$confirm('切换判题方式后需要重新上传测试数据，是否继续？', '提示', {
            confirmButtonText: '继续',
            cancelButtonText: '取消',
            type: 'warning'
          }).then(() => {
            this.problem.spj = !this.problem.spj
            this.resetTestCase()
          }).catch(() => {
          })
        } else {
          this.problem.spj = !this.problem.spj
        }
      },
      querySearch (queryString, cb) {
        api.getProblemTagList({ keyword: queryString }).then(res => {
          let tagList = []
          for (let tag of res.data.data) {
            tagList.push({value: tag.name})
          }
          cb(tagList)
        }).catch(() => {
        })
      },
      resetTestCase () {
        this.testCaseUploaded = false
        this.problem.test_case_score = []
        this.problem.test_case_id = ''
      },
      addTag () {
        let inputValue = this.tagInput
        if (inputValue) {
          this.problem.tags.push(inputValue)
        }
        this.inputVisible = false
        this.tagInput = ''
      },
      closeTag (tag) {
        this.problem.tags.splice(this.problem.tags.indexOf(tag), 1)
      },
      addSample () {
        this.problem.samples.push({input: '', output: ''})
      },
      deleteSample (index) {
        this.problem.samples.splice(index, 1)
      },
      uploadSucceeded (response) {
        if (response.error) {
          this.$error(response.data)
          return
        }
        let fileList = response.data.info
        for (let file of fileList) {
          file.score = (100 / fileList.length).toFixed(0)
          if (!file.output_name && this.problem.spj) {
            file.output_name = '-'
          }
        }
        this.problem.test_case_score = fileList
        this.testCaseUploaded = true
        this.problem.test_case_id = response.data.id
      },
      uploadFailed () {
        this.$error('上传失败')
      },
      compileSPJ () {
        let data = {
          id: this.problem.id,
          spj_code: this.problem.spj_code,
          spj_language: this.problem.spj_language
        }
        this.loadingCompile = true
        api.compileSPJ(data).then(res => {
          this.loadingCompile = false
          this.problem.spj_compile_ok = true
          this.compiledSpj = {code: data.spj_code, language: data.spj_language}
          if (this.problem.spj_code !== data.spj_code || this.problem.spj_language !== data.spj_language) {
            this.problem.spj_compile_ok = false
          }
          this.error.spj = ''
        }, err => {
          this.loadingCompile = false
          this.problem.spj_compile_ok = false
          this.$msgbox({
            title: '编译错误',
            type: 'error',
            message: h('pre', apiErrorMessage(err)),
            showCancelButton: false,
            closeOnClickModal: false,
            customClass: 'dialog-compile-error'
          })
        })
      },
      submit () {
        if (this.problem.judge_mode !== 'REMOTE' && !this.problem.samples.length) {
          this.$error('请至少添加一组样例')
          return
        }
        for (let sample of this.problem.samples) {
          if (!sample.input || !sample.output) {
            this.$error('样例输入和输出不能为空')
            return
          }
        }
        if (!this.problem.tags.length) {
          this.error.tags = '请至少添加一个标签'
          this.$error(this.error.tags)
          return
        }
        if (this.problem.spj) {
          if (!this.problem.spj_code) {
            this.error.spj = '请输入 Special Judge 代码'
            this.$error(this.error.spj)
          } else if (!this.problem.spj_compile_ok) {
            this.error.spj = 'Special Judge 代码尚未编译成功'
          }
          if (this.error.spj) {
            this.$error(this.error.spj)
            return
          }
        }
        if (!this.problem.languages.length) {
          this.error.languages = '请至少选择一种编程语言'
          this.$error(this.error.languages)
          return
        }
        if (this.problem.judge_mode !== 'REMOTE' && !this.testCaseUploaded) {
          this.error.testCase = '尚未上传测试数据'
          this.$error(this.error.testCase)
          return
        }
        if (this.problem.rule_type === 'OI') {
          for (let item of this.problem.test_case_score) {
            try {
              if (parseInt(item.score) <= 0) {
                this.$error('测试点分数无效')
                return
              }
            } catch (e) {
              this.$error('测试点分数必须是整数')
              return
            }
          }
        }
        this.problem.languages = this.problem.languages.sort()
        let funcName = {
          'create-problem': 'createProblem',
          'edit-problem': 'editProblem',
          'create-contest-problem': 'createContestProblem',
          'edit-contest-problem': 'editContestProblem'
        }[this.routeName]
        // edit contest problem 时, contest_id会被后来的请求覆盖掉
        if (funcName === 'editContestProblem') {
          this.problem.contest_id = this.contest.id
        }
        api[funcName](this.problem).then(res => {
          if (this.routeName === 'create-contest-problem' || this.routeName === 'edit-contest-problem') {
            this.$router.push({name: 'contest-problem-list', params: {contestId: this.$route.params.contestId}})
          } else {
            this.$router.push({name: 'problem-list'})
          }
        }).catch(() => {
        })
      }
    }
  }
</script>

<style lang="less" scoped>
  .problem { --form-gap: 18px; }
  .remote-alert { margin-bottom: 18px; }
  .problem-form { display: grid; gap: 18px; }
  .form-section { padding: 20px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg); }
  .section-heading, .subsection-heading, .sample-card-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
  .section-heading { margin-bottom: 18px; }
  .section-heading h3 { margin: 0; color: var(--color-text); font-size: 16px; font-weight: 680; }
  .section-heading p { margin: 4px 0 0; color: var(--color-text-muted); font-size: 12px; line-height: 1.55; }
  .section-heading.is-inline > :last-child { flex: none; }
  .field-grid { display: grid; gap: 0 var(--form-gap); }
  .basic-grid { grid-template-columns: minmax(0, 3fr) minmax(220px, 1fr); }
  .limit-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .metadata-grid, .statement-grid, .sample-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .judge-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .full-control { width: 100%; }
  .tag-editor { display: flex; min-height: 32px; align-items: center; flex-wrap: wrap; gap: 7px; }
  .tags { display: flex; flex-wrap: wrap; gap: 6px; }
  .input-new-tag { width: 110px; }
  .button-new-tag { min-height: 28px; }
  .language-options { display: flex; align-items: center; flex-wrap: wrap; gap: 2px 14px; }
  .toggle-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .toggle-field { display: flex; min-height: 62px; align-items: center; justify-content: space-between; gap: 16px; padding: 11px 13px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg-subtle); }
  .toggle-field span, .toggle-field strong, .toggle-field small { display: block; }
  .toggle-field strong { color: var(--color-text); font-size: 13px; }
  .toggle-field small { margin-top: 3px; color: var(--color-text-muted); font-size: 11px; }
  .sample-list { display: grid; gap: 12px; }
  .sample-card { padding: 14px 15px 2px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg-subtle); }
  .sample-card-heading { margin-bottom: 10px; }
  .sample-card-heading strong { color: var(--color-text); font-size: 13px; }
  .spj-editor-card { margin: 2px 0 18px; overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
  .subsection-heading { min-height: 48px; padding: 8px 10px 8px 14px; border-bottom: 1px solid var(--color-border); background: var(--color-bg-subtle); }
  .subsection-heading strong { color: var(--color-text); font-size: 13px; }
  .subsection-actions { display: flex; align-items: center; gap: 8px; }
  .spj-language-select { width: 132px; }
  .testcase-error { margin-bottom: 12px; }
  .testcase-table { width: 100%; }
  .form-actions { display: flex; justify-content: flex-end; padding: 2px 0 6px; }

  :deep(.el-form-item) { min-width: 0; }
  :deep(.el-form-item__label) { color: var(--color-text-muted); font-size: 12px; font-weight: 620; }
  :deep(.el-input), :deep(.el-select), :deep(.el-textarea) { width: 100%; }

  @media (max-width: 1100px) {
    .limit-grid, .judge-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }

  @media (max-width: 760px) {
    .form-section { padding: 15px; }
    .basic-grid, .limit-grid, .metadata-grid, .statement-grid, .sample-grid, .judge-grid, .toggle-row { grid-template-columns: 1fr; }
    .section-heading { align-items: flex-start; }
    .section-heading.is-inline { flex-direction: column; }
  }
</style>

<style>
  .problem-tag-poper {
    width: 200px !important;
  }
  .dialog-compile-error {
    width: auto;
    max-width: 80%;
    overflow-x: scroll;
  }
</style>
