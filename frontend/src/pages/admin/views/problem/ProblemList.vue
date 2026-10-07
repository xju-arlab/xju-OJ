<template>
  <div class="view">
    <Panel :title="contestId ? this.$t('m.Contest_Problem_List') : this.$t('m.Problem_List')">
      <template #header><div >
        <el-input
          v-model="keyword"
          placeholder="搜索题目">
          <template #prefix><Icon type="search" /></template>
        </el-input>
      </div></template>
      <el-table
        v-loading="loading"
        element-loading-text="正在加载"
        ref="table"
        :data="problemList"
        @row-dblclick="handleDblclick"
        style="width: 100%">
        <el-table-column
          width="100"
          prop="id"
          label="ID">
        </el-table-column>
        <el-table-column
          width="150"
          label="显示 ID">
          <template #default="{row}">
            <span>{{row._id}}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="title"
          label="标题">
          <template #default="{row}">
            <span v-show="!row.isEditing">{{row.title}}</span>
            <el-input v-show="row.isEditing" v-model="row.title"
                      @keyup.enter="handleInlineEdit(row)">
            </el-input>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_by.username"
          label="创建者">
        </el-table-column>
        <el-table-column
          width="200"
          prop="create_time"
          label="创建时间">
          <template #default="scope">
            {{ $filters.localtime(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column
          width="100"
          prop="visible"
          label="可见">
          <template #default="scope">
            <el-switch v-model="scope.row.visible"
                       active-text=""
                       inactive-text=""
                       @change="updateProblem(scope.row)">
            </el-switch>
          </template>
        </el-table-column>
        <el-table-column
          width="120"
          label="判题方式">
          <template #default="scope">
            {{ scope.row.judge_mode === 'REMOTE' ? providerLabel(scope.row.remote_oj) : '本地判题' }}
          </template>
        </el-table-column>
        <el-table-column
          fixed="right"
          label="操作"
          width="168">
          <template #default="scope"><div >
            <icon-btn name="编辑" icon="edit" @click="goEdit(scope.row.id)"></icon-btn>
            <icon-btn v-if="contestId" name="加入公共题库" icon="clone"
                      @click="makeContestProblemPublic(scope.row.id)"></icon-btn>
            <icon-btn v-if="scope.row.judge_mode !== 'REMOTE'"
                      icon="download" name="下载测试数据"
                      @click="downloadTestCase(scope.row.id)"></icon-btn>
            <icon-btn danger icon="trash" name="删除题目"
                      @click="deleteProblem(scope.row.id)"></icon-btn>
          </div></template>
        </el-table-column>
      </el-table>
      <div class="panel-options">
        <el-button type="primary" size="small"
                   @click="goCreateProblem"><Icon type="plus" />新建题目
        </el-button>
        <el-button v-if="!contestId" type="success" size="small"
                   @click="remoteImportDialogVisible = true"><Icon type="download" />导入外部题目
        </el-button>
        <el-button v-if="contestId" type="success" size="small"
                   @click="remoteImportDialogVisible = true"><Icon type="download" />导入外部题目
        </el-button>
        <el-button v-if="contestId" type="primary"
                   size="small"
                   @click="addProblemDialogVisible = true"><Icon type="plus" />从公共题库添加
        </el-button>
        <el-pagination
          class="page"
          layout="prev, pager, next"
          @current-change="currentChange"
          :page-size="pageSize"
          :total="total">
        </el-pagination>
      </div>
    </Panel>
    <LegacyDialog title="确认更新题目？"
               width="20%"
               :visible="InlineEditDialogVisible" @update:visible="InlineEditDialogVisible = $event"
               @close-on-click-modal="false">
      <div>
        <p>显示 ID：{{currentRow._id}}</p>
        <p>标题：{{currentRow.title}}</p>
      </div>
      <template #footer><span >
        <cancel @click="InlineEditDialogVisible = false; getProblemList(currentPage)"></cancel>
        <save @click="updateProblem(currentRow)"></save>
      </span></template>
    </LegacyDialog>
    <LegacyDialog title="添加比赛题目"
               v-if="contestId"
               width="80%"
               :visible="addProblemDialogVisible" @update:visible="addProblemDialogVisible = $event"
               @close-on-click-modal="false">
      <add-problem-component :contestID="contestId" @on-change="getProblemList"></add-problem-component>
    </LegacyDialog>
    <LegacyDialog :title="contestId ? '导入外部题目到比赛' : '导入外部题目'"
               width="520px"
               :visible="remoteImportDialogVisible" @update:visible="remoteImportDialogVisible = $event"
               @close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="来源平台" required>
          <el-select v-model="remoteImportForm.provider" style="width: 100%">
            <el-option label="Nowcoder / 牛客" value="NOWCODER"></el-option>
            <el-option label="Luogu / 洛谷" value="LUOGU"></el-option>
            <el-option label="Codeforces" value="CODEFORCES"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="题目链接" required>
          <el-input v-model="remoteImportForm.remote_id"
                    placeholder="题目链接"></el-input>
        </el-form-item>
        <el-alert type="info" :closable="false"
                  :title="contestId
                    ? '首次导入的外部题目将在比赛结束后自动进入公共题库。'
                    : '导入完成后即可用于远程练习提交。'"></el-alert>
      </el-form>
      <template #footer><span>
        <cancel @click="remoteImportDialogVisible = false"></cancel>
        <el-button type="primary" :loading="remoteImportLoading"
                   @click="importRemoteProblem">导入</el-button>
      </span></template>
    </LegacyDialog>
  </div>
</template>
<script>
  import api from '../../api.js'
  import utils from '@/utils/utils'
  import AddProblemComponent from './AddPublicProblem.vue'
  import { collectCodeforcesProblemPage, supportsRemoteProblemImport } from '../../remoteBridge'

  export default {
    name: 'ProblemList',
    components: {
      AddProblemComponent
    },
    data () {
      return {
        pageSize: 10,
        total: 0,
        problemList: [],
        keyword: '',
        loading: false,
        currentPage: 1,
        routeName: '',
        contestId: '',
        // for make public use
        currentProblemID: '',
        currentRow: {},
        InlineEditDialogVisible: false,
        makePublicDialogVisible: false,
        addProblemDialogVisible: false,
        remoteImportDialogVisible: false,
        remoteImportLoading: false,
        remoteImportForm: {
          provider: 'NOWCODER',
          remote_id: ''
        }
      }
    },
    mounted () {
      this.routeName = this.$route.name
      this.contestId = this.$route.params.contestId
      this.getProblemList(this.currentPage)
    },
    methods: {
      providerLabel (provider) {
        return {
          NOWCODER: '牛客',
          LUOGU: '洛谷',
          CODEFORCES: 'Codeforces'
        }[provider] || provider
      },
      handleDblclick (row) {
        row.isEditing = true
      },
      goEdit (problemId) {
        if (this.routeName === 'problem-list') {
          this.$router.push({name: 'edit-problem', params: {problemId}})
        } else if (this.routeName === 'contest-problem-list') {
          this.$router.push({name: 'edit-contest-problem', params: {problemId: problemId, contestId: this.contestId}})
        }
      },
      goCreateProblem () {
        if (this.routeName === 'problem-list') {
          this.$router.push({name: 'create-problem'})
        } else if (this.routeName === 'contest-problem-list') {
          this.$router.push({name: 'create-contest-problem', params: {contestId: this.contestId}})
        }
      },
      async importRemoteProblem () {
        if (!this.remoteImportForm.remote_id.trim()) {
          this.$error('请输入题目链接')
          return
        }
        this.remoteImportLoading = true
        let pageHtml = ''
        if (this.remoteImportForm.provider === 'CODEFORCES') {
          if (!supportsRemoteProblemImport()) {
            this.remoteImportLoading = false
            this.$error('Codeforces 导题需要最新版远程提交助手，已为你打开安装页')
            window.open('/remote-bridge', '_blank', 'noopener')
            return
          }
          try {
            pageHtml = await collectCodeforcesProblemPage(this.remoteImportForm.remote_id.trim())
          } catch (error) {
            this.remoteImportLoading = false
            this.$error(error.message || 'Codeforces 题面读取失败')
            return
          }
        }
        api.importRemoteProblem({
          provider: this.remoteImportForm.provider,
          remote_id: this.remoteImportForm.remote_id.trim(),
          contest_id: this.contestId || null,
          page_html: pageHtml
        }).then(() => {
          this.remoteImportLoading = false
          this.remoteImportDialogVisible = false
          this.remoteImportForm = {
            provider: 'NOWCODER',
            remote_id: ''
          }
          this.$success('外部题目导入成功')
          this.getProblemList(1)
        }).catch(() => {
          this.remoteImportLoading = false
        })
      },
      // 切换页码回调
      currentChange (page) {
        this.currentPage = page
        this.getProblemList(page)
      },
      getProblemList (page = 1) {
        this.loading = true
        let funcName = this.routeName === 'problem-list' ? 'getProblemList' : 'getContestProblemList'
        let params = {
          limit: this.pageSize,
          offset: (page - 1) * this.pageSize,
          keyword: this.keyword,
          contest_id: this.contestId
        }
        api[funcName](params).then(res => {
          this.loading = false
          this.total = res.data.data.total
          for (let problem of res.data.data.results) {
            problem.isEditing = false
          }
          this.problemList = res.data.data.results
        }, res => {
          this.loading = false
        })
      },
      deleteProblem (id) {
        this.$confirm('确定删除这道题目吗？相关提交记录也会一并删除。', '删除题目', {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        }).then(() => {
          let funcName = this.routeName === 'problem-list' ? 'deleteProblem' : 'deleteContestProblem'
          api[funcName](id).then(() => {
            const page = this.problemList.length === 1 && this.currentPage > 1
              ? this.currentPage - 1
              : this.currentPage
            this.currentPage = page
            this.getProblemList(page)
          }).catch(() => {})
        }, () => {
        })
      },
      makeContestProblemPublic (problemID) {
        this.$confirm('确定将该题加入公共题库吗？题号将由系统自动分配。', '确认').then(() => {
          api.makeContestProblemPublic({id: problemID}).then(() => {
            this.$success('题目已加入公共题库')
            this.getProblemList(this.currentPage)
          }).catch(() => {})
        }).catch(() => {})
      },
      updateProblem (row) {
        let data = Object.assign({}, row)
        let funcName = ''
        if (this.contestId) {
          data.contest_id = this.contestId
          funcName = 'editContestProblem'
        } else {
          funcName = 'editProblem'
        }
        api[funcName](data).then(res => {
          this.InlineEditDialogVisible = false
          this.getProblemList(this.currentPage)
        }).catch(() => {
          this.InlineEditDialogVisible = false
        })
      },
      handleInlineEdit (row) {
        this.currentRow = row
        this.InlineEditDialogVisible = true
      },
      downloadTestCase (problemID) {
        let url = '/admin/test_case?problem_id=' + problemID
        utils.downloadFile(url)
      },
      getPublicProblem () {
        api.getProblemList()
      }
    },
    watch: {
      '$route' (newVal, oldVal) {
        this.contestId = newVal.params.contestId
        this.routeName = newVal.name
        this.getProblemList(this.currentPage)
      },
      'keyword' () {
        this.currentChange(1)
      }
    }
  }
</script>

<style scoped lang="less">
</style>
