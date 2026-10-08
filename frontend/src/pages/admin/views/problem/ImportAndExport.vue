<template>
  <div>
    <nav class="import-kind-tabs" aria-label="导入题库类型"><router-link to="/problem/batch_ops" :class="{ active: !isAI }">普通题目</router-link><router-link to="/ai/problem/batch_ops" :class="{ active: isAI }">AI 题目</router-link></nav>
    <AIImportAndExport v-if="isAI" />
    <template v-else>
    <panel title="导出题目（测试版）">
      <template #header><div >
        <el-input
          v-model="keyword"
          placeholder="搜索题目">
          <template #prefix><Icon type="search" /></template>
        </el-input>
      </div></template>
      <el-table :data="problems"
                v-loading="loadingProblems" @selection-change="handleSelectionChange">
        <el-table-column
          type="selection"
          width="60">
        </el-table-column>
        <el-table-column
          label="ID"
          width="100"
          prop="id">
        </el-table-column>
        <el-table-column
          label="显示 ID"
          width="200"
          prop="_id">
        </el-table-column>
        <el-table-column
          label="标题"
          prop="title">
        </el-table-column>
        <el-table-column
          prop="created_by.username"
          label="创建者">
        </el-table-column>
        <el-table-column
          prop="create_time"
          label="创建时间">
          <template #default="scope">
            {{ $filters.localtime(scope.row.create_time) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="panel-options">
        <el-button type="primary" size="small" v-show="selected_problems.length"
                   @click="exportProblems"><Icon type="arrow-down" />导出
        </el-button>
        <el-pagination
          class="page"
          layout="prev, pager, next"
          @current-change="getProblems"
          :page-size="limit"
          :total="total">
        </el-pagination>
      </div>
    </panel>
    <panel title="导入外部 OJ 题目">
      <div class="remote-import-grid">
        <article v-for="provider in remoteProviders"
                 :key="provider.value"
                 :class="['remote-import-card', `provider-${provider.value.toLowerCase()}`]">
          <div class="remote-card-heading">
            <span>{{ provider.short }}</span>
            <div><strong>{{ provider.name }}</strong><small>{{ provider.description }}</small></div>
          </div>
          <el-input v-model="remoteImports[provider.value]" :placeholder="provider.placeholder"></el-input>
          <el-button type="primary"
                     :loading="remoteImportLoading[provider.value]"
                     @click="importRemoteProblem(provider.value)">导入 {{ provider.name }}</el-button>
        </article>
      </div>
    </panel>
    <panel title="导入 ZIP 题库">
      <p class="import-description">
        支持根目录单题 ZIP、由多个单题 ZIP 组成的批量 ZIP。
      </p>
      <el-upload class="import-upload"
        ref="QDU"
        action="/api/admin/import_problem"
        :headers="csrfHeaders()"
        name="file"
        accept=".zip,application/zip"
        :file-list="fileList1"
        :show-file-list="true"
        :with-credentials="true"
        :limit="1"
        :on-change="onFile1Change"
        :auto-upload="false"
        :on-success="uploadSucceeded"
        :on-error="uploadFailed">
        <template #trigger><el-button size="small" type="primary"><Icon type="upload" />选择文件</el-button></template>
        <el-button size="small" type="success" @click="submitUpload('QDU')"><Icon type="upload" />上传</el-button>
      </el-upload>
    </panel>

    <panel title="导入 FPS 题目（测试版）">
      <el-upload class="import-upload"
        ref="FPS"
        action="/api/admin/import_fps"
        :headers="csrfHeaders()"
        name="file"
        :file-list="fileList2"
        :show-file-list="true"
        :with-credentials="true"
        :limit="3"
        :on-change="onFile2Change"
        :auto-upload="false"
        :on-success="uploadSucceeded"
        :on-error="uploadFailed">
        <template #trigger><el-button size="small" type="primary"><Icon type="upload" />选择文件</el-button></template>
        <el-button size="small" type="success" @click="submitUpload('FPS')"><Icon type="upload" />上传</el-button>
      </el-upload>
    </panel>
    </template>
  </div>
</template>
<script>
  import AIImportAndExport from '../ai/ImportAndExport.vue'
  import api from '@admin/api'
  import { csrfHeaders } from '@/utils/csrf'
  import utils from '@/utils/utils'
  import { collectCodeforcesProblemPage, supportsRemoteProblemImport } from '../../remoteBridge'

  const remoteProviders = [
    { value: 'NOWCODER', short: 'NC', name: '牛客', description: '导入公开编程题并绑定牛客远程判题', placeholder: '题目链接' },
    { value: 'LUOGU', short: 'LG', name: '洛谷', description: '导入洛谷公开题面与样例', placeholder: '题目链接' },
    { value: 'CODEFORCES', short: 'CF', name: 'Codeforces', description: '通过远程助手读取 Codeforces 题面', placeholder: '题目链接' }
  ]

  export default {
    components: { AIImportAndExport },
    computed: { isAI () { return this.$route.path.startsWith('/ai/') } },
    name: 'import_and_export',
    data () {
      return {
        fileList1: [],
        fileList2: [],
        page: 1,
        limit: 10,
        total: 0,
        loadingProblems: false,
        loadingImporting: false,
        remoteProviders,
        remoteImports: { NOWCODER: '', LUOGU: '', CODEFORCES: '' },
        remoteImportLoading: { NOWCODER: false, LUOGU: false, CODEFORCES: false },
        keyword: '',
        problems: [],
        selected_problems: []
      }
    },
    mounted () {
      if (!this.isAI) this.getProblems()
    },
    methods: {
      csrfHeaders,
      handleSelectionChange (val) {
        this.selected_problems = val
      },
      getProblems (page = 1) {
        let params = {
          keyword: this.keyword,
          offset: (page - 1) * this.limit,
          limit: this.limit
        }
        this.loadingProblems = true
        api.getProblemList(params).then(res => {
          this.problems = res.data.data.results
          this.total = res.data.data.total
          this.loadingProblems = false
        })
      },
      exportProblems () {
        let params = []
        for (let p of this.selected_problems) {
          params.push('problem_id=' + p.id)
        }
        let url = '/admin/export_problem?' + params.join('&')
        utils.downloadFile(url)
      },
      async importRemoteProblem (provider) {
        const reference = this.remoteImports[provider].trim()
        if (!reference) {
          this.$error('请输入题目链接')
          return
        }
        this.remoteImportLoading[provider] = true
        try {
          let pageHtml = ''
          if (provider === 'CODEFORCES') {
            if (!supportsRemoteProblemImport()) throw new Error('Codeforces 导题需要最新版远程提交助手')
            pageHtml = await collectCodeforcesProblemPage(reference)
          }
          await api.importRemoteProblem({
            provider,
            remote_id: reference,
            contest_id: null,
            page_html: pageHtml
          })
          this.remoteImports[provider] = ''
          this.$success('外部题目导入成功')
          this.getProblems(1)
        } catch (error) {
          this.$error(error.message || '外部题目导入失败')
        } finally {
          this.remoteImportLoading[provider] = false
        }
      },
      submitUpload (ref) {
        this.$refs[ref].submit()
      },
      onFile1Change (file, fileList) {
        this.fileList1 = fileList.slice(-1)
      },
      onFile2Change (file, fileList) {
        this.fileList2 = fileList.slice(-1)
      },
      uploadSucceeded (response) {
        if (response.error) {
          this.$error(response.data)
        } else {
          this.$success(`成功导入 ${response.data.import_count} 道题目`)
          this.fileList1 = []
          this.getProblems()
        }
      },
      uploadFailed () {
        this.$error('上传失败')
      }
    },
    watch: {
      'keyword' () {
        this.getProblems()
      }
    }
  }
</script>

<style scoped lang="less">
  .import-kind-tabs { display: flex; gap: 24px; margin-bottom: 20px; padding: 0 20px; border-bottom: 1px solid var(--color-border); }
  .import-kind-tabs a { padding: 12px 0; color: var(--color-text-muted); border-bottom: 2px solid transparent; }
  .import-kind-tabs a.active { color: var(--color-text); border-bottom-color: var(--color-text); font-weight: 600; }
  :deep(.import-upload) {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  :deep(.import-upload .el-upload-list) {
    flex: 0 0 100%;
    margin: 4px 0 0;
  }
  .import-description { margin: 0 0 12px; color: var(--color-text-muted); line-height: 1.7; }
  .remote-import-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
  .remote-import-card { display: flex; min-width: 0; min-height: 214px; flex-direction: column; gap: 14px; padding: 16px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg); }
  .remote-card-heading { display: flex; align-items: center; gap: 11px; }
  .remote-card-heading > span { display: inline-grid; width: 38px; height: 38px; flex: none; place-items: center; border-radius: var(--radius-sm); background: var(--color-bg-subtle); color: var(--color-text); font-size: 12px; font-weight: 750; }
  .remote-card-heading strong, .remote-card-heading small { display: block; }
  .remote-card-heading strong { color: var(--color-text); font-size: 15px; }
  .remote-card-heading small { margin-top: 3px; color: var(--color-text-muted); font-size: 11px; line-height: 1.45; }
  .remote-import-card > .el-button { width: 100%; margin-top: auto; }
  .provider-nowcoder .remote-card-heading > span { background: var(--tag-course-bg); color: var(--cat-course); }
  .provider-luogu .remote-card-heading > span { background: var(--tag-tools-bg); color: var(--cat-tools); }
  .provider-codeforces .remote-card-heading > span { background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
  @media (max-width: 1000px) { .remote-import-grid { grid-template-columns: 1fr; } }
</style>
