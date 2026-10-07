<template>
  <div class="view">
    <Panel title="比赛列表">
      <template #header><div >
        <el-input
          v-model="keyword"
          placeholder="搜索比赛">
          <template #prefix><Icon type="search" /></template>
        </el-input>
      </div></template>
      <el-table
        v-loading="loading"
        element-loading-text="正在加载"
        ref="table"
        :data="contestList"
        style="width: 100%">
        <el-table-column type="expand">
          <template #default="props">
            <p>开始时间：{{ $filters.localtime(props.row.start_time) }}</p>
            <p>结束时间：{{ $filters.localtime(props.row.end_time) }}</p>
            <p>创建时间：{{ $filters.localtime(props.row.create_time) }}</p>
            <p>创建者：{{props.row.created_by.username}}</p>
          </template>
        </el-table-column>
        <el-table-column
          prop="id"
          width="80"
          label="ID">
        </el-table-column>
        <el-table-column
          prop="title"
          label="标题">
        </el-table-column>
        <el-table-column
          label="规则"
          width="130">
          <template #default="scope"><span class="contest-rule" :class="'is-' + String(scope.row.rule_type || '').toLowerCase()">{{scope.row.rule_type}}</span></template>
        </el-table-column>
        <el-table-column
          label="比赛类型"
          width="180">
          <template #default="scope">
            <el-tag :type="scope.row.contest_type === 'Public' ? 'success' : 'primary'">
              {{ scope.row.contest_type === 'Public' ? '公开比赛' : '密码比赛' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="状态"
          width="130">
          <template #default="scope">
            <el-tag
              :type="scope.row.status === '-1' ? 'danger' : scope.row.status === '0' ? 'success' : 'primary'">
              {{ $filters.contestStatus(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          width="100"
          label="可见">
          <template #default="scope">
            <el-switch v-model="scope.row.visible"
                       active-text=""
                       inactive-text=""
                       @change="handleVisibleSwitch(scope.row)">
            </el-switch>
          </template>
        </el-table-column>
        <el-table-column
          fixed="right"
          width="184"
          label="操作">
          <template #default="scope"><div class="contest-operation-actions">
            <icon-btn name="编辑" icon="edit" @click="goEdit(scope.row.id)"></icon-btn>
            <icon-btn name="题目" icon="list-ol" @click="scope.row.rule_type === 'AI' ? goEdit(scope.row.id) : goContestProblemList(scope.row.id)"></icon-btn>
            <icon-btn name="公告" icon="info-circle"
                      @click="goContestAnnouncement(scope.row.id)"></icon-btn>
            <icon-btn v-if="scope.row.rule_type !== 'AI'" icon="download" name="下载通过的提交"
                      @click="openDownloadOptions(scope.row.id)"></icon-btn>
            <icon-btn danger icon="trash" name="删除比赛"
                      @click="deleteContest(scope.row.id)"></icon-btn>
          </div></template>
        </el-table-column>
      </el-table>
      <div class="panel-options">
        <el-pagination
          class="page"
          layout="prev, pager, next"
          @current-change="currentChange"
          :page-size="pageSize"
          :total="total">
        </el-pagination>
      </div>
    </Panel>
    <LegacyDialog title="下载比赛提交"
               width="30%"
               :visible="downloadDialogVisible" @update:visible="downloadDialogVisible = $event">
      <el-switch v-model="excludeAdmin" active-text="排除管理员提交"></el-switch>
      <template #footer><span  class="dialog-footer">
        <el-button type="primary" @click="downloadSubmissions">确 定</el-button>
      </span></template>
    </LegacyDialog>
  </div>
</template>
<script>
  import api from '../../api.js'
  import utils from '@/utils/utils'
  import {CONTEST_STATUS_REVERSE} from '@/utils/constants'

  export default {
    name: 'ContestList',
    data () {
      return {
        pageSize: 10,
        total: 0,
        contestList: [],
        keyword: '',
        loading: false,
        excludeAdmin: true,
        currentPage: 1,
        currentId: 1,
        downloadDialogVisible: false
      }
    },
    mounted () {
      this.getContestList(this.currentPage)
    },
    filters: {
      contestStatus (value) {
        return CONTEST_STATUS_REVERSE[value].name
      }
    },
    methods: {
      // 切换页码回调
      currentChange (page) {
        this.currentPage = page
        this.getContestList(page)
      },
      getContestList (page) {
        this.loading = true
        api.getContestList((page - 1) * this.pageSize, this.pageSize, this.keyword).then(res => {
          this.loading = false
          this.total = res.data.data.total
          this.contestList = res.data.data.results
        }, res => {
          this.loading = false
        })
      },
      openDownloadOptions (contestId) {
        this.downloadDialogVisible = true
        this.currentId = contestId
      },
      downloadSubmissions () {
        let excludeAdmin = this.excludeAdmin ? '1' : '0'
        let url = `/admin/download_submissions?contest_id=${this.currentId}&exclude_admin=${excludeAdmin}`
        utils.downloadFile(url)
      },
      goEdit (contestId) {
        this.$router.push({name: 'edit-contest', params: {contestId}})
      },
      goContestAnnouncement (contestId) {
        this.$router.push({name: 'contest-announcement', params: {contestId}})
      },
      goContestProblemList (contestId) {
        this.$router.push({name: 'contest-problem-list', params: {contestId}})
      },
      handleVisibleSwitch (row) {
        api.editContest(row)
      },
      deleteContest (contestId) {
        this.$confirm('确定删除这场比赛吗？比赛题目、提交、排名和报名记录都会一并删除。', '删除比赛', {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        }).then(() => {
          api.deleteContest(contestId).then(() => {
            const page = this.contestList.length === 1 && this.currentPage > 1
              ? this.currentPage - 1
              : this.currentPage
            this.currentPage = page
            this.getContestList(page)
          }).catch(() => {})
        }).catch(() => {})
      }
    },
    watch: {
      'keyword' () {
        this.currentChange(1)
      }
    }
  }
</script>
<style scoped lang="less">
.contest-rule { font-size: 13px; font-weight: 700; letter-spacing: .02em; }
.contest-rule.is-oi { color: #7656c9; }
.contest-rule.is-acm { color: #b7791f; }
.contest-rule.is-ai { color: #2873be; }
.contest-operation-actions { display: flex; align-items: center; flex-wrap: nowrap; white-space: nowrap; }
</style>
