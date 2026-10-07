<template>
  <div class="view">
    <Panel :title="$t('m.User_User') ">
      <template #header><div >
        <el-row :gutter="20">
          <el-col :span="8">
            <el-button v-show="selectedUsers.length"
                       type="warning"
                       @click="deleteUsers(selectedUserIDs)"><Icon type="trash" />删除
            </el-button>
          </el-col>
          <el-col :span="selectedUsers.length ? 16: 24">
            <el-input v-model="keyword" placeholder="搜索用户"><template #prefix><Icon type="search" /></template></el-input>
          </el-col>
        </el-row>
      </div></template>
      <el-table
        v-loading="loadingTable"
        element-loading-text="正在加载"
        @selection-change="handleSelectionChange"
        ref="table"
        :data="userList"
        style="width: 100%">
        <el-table-column type="selection" width="55"></el-table-column>

        <el-table-column prop="id" label="ID"></el-table-column>

        <el-table-column prop="username" label="用户名"></el-table-column>

        <el-table-column prop="create_time" label="创建时间">
          <template #default="scope">
            {{ $filters.localtime(scope.row.create_time) }}
          </template>
        </el-table-column>

        <el-table-column prop="last_login" label="最后登录">
          <template #default="scope">
            {{ $filters.localtime(scope.row.last_login) }}
          </template>
        </el-table-column>

        <el-table-column prop="real_name" label="真实姓名"></el-table-column>

        <el-table-column prop="email" label="邮箱"></el-table-column>

        <el-table-column prop="admin_type" label="用户类型">
          <template #default="scope">
            {{ {'Regular User': '普通用户', 'Admin': '管理员', 'Super Admin': '超级管理员'}[scope.row.admin_type] || scope.row.admin_type }}
          </template>
        </el-table-column>

        <el-table-column fixed="right" label="操作" width="96">
          <template #default="{row}">
            <icon-btn name="编辑" icon="edit" @click="openUserDialog(row.id)"></icon-btn>
            <icon-btn danger name="删除" icon="trash" @click="deleteUsers([row.id])"></icon-btn>
          </template>
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

    <Panel>
      <template #title><span >{{$t('m.Import_User')}}
        <el-popover placement="right" trigger="hover">
          <p>仅支持不含表头的 CSV 文件，格式依次为用户名、密码、邮箱和真实姓名。</p>
          <template #reference><Icon type="question-circle" class="import-user-icon" /></template>
        </el-popover>
      </span></template>
      <el-upload v-if="!uploadUsers.length"
                 action=""
                 :show-file-list="false"
                 accept=".csv"
                 :before-upload="handleUsersCSV">
        <el-button size="small" type="primary"><Icon type="upload" />选择文件</el-button>
      </el-upload>
      <template v-else>
        <el-table :data="uploadUsersPage">
          <el-table-column label="用户名">
            <template #default="{row}">
              {{row[0]}}
            </template>
          </el-table-column>
          <el-table-column label="密码">
            <template #default="{row}">
              {{row[1]}}
            </template>
          </el-table-column>
          <el-table-column label="邮箱">
            <template #default="{row}">
              {{row[2]}}
            </template>
          </el-table-column>
          <el-table-column label="真实姓名">
            <template #default="{row}">
              {{row[3]}}
            </template>
          </el-table-column>
        </el-table>
        <div class="panel-options">
          <el-button type="primary" size="small"
                     @click="handleUsersUpload"><Icon type="upload" />全部导入
          </el-button>
          <el-button type="warning" size="small"
                     @click="handleResetData"><Icon type="undo" />重置数据
          </el-button>
          <el-pagination
            class="page"
            layout="prev, pager, next"
            :page-size="uploadUsersPageSize"
            :current-page="uploadUsersCurrentPage" @update:current-page="uploadUsersCurrentPage = $event"
            :total="uploadUsers.length">
          </el-pagination>
        </div>
      </template>
    </Panel>

    <Panel :title="$t('m.Generate_User')">
      <el-form :model="formGenerateUser" ref="formGenerateUser">
        <el-row type="flex" justify="space-between">
          <el-col :span="4">
            <el-form-item label="前缀" prop="prefix">
              <el-input v-model="formGenerateUser.prefix" placeholder="用户名前缀"></el-input>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="后缀" prop="suffix">
              <el-input v-model="formGenerateUser.suffix" placeholder="用户名后缀"></el-input>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="起始编号" prop="number_from" required>
              <el-input-number v-model="formGenerateUser.number_from" style="width: 100%"></el-input-number>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="结束编号" prop="number_to" required>
              <el-input-number v-model="formGenerateUser.number_to" style="width: 100%"></el-input-number>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="密码长度" prop="password_length" required>
              <el-input v-model="formGenerateUser.password_length"
                        placeholder="密码长度"></el-input>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-button type="primary" @click="generateUser" :loading="loadingGenerate"><Icon type="users" />生成并导出
          </el-button>
          <span class="userPreview" v-if="formGenerateUser.number_from && formGenerateUser.number_to &&
                                          formGenerateUser.number_from <= formGenerateUser.number_to">
            将生成用户名：{{formGenerateUser.prefix + formGenerateUser.number_from + formGenerateUser.suffix}}、
            <span v-if="formGenerateUser.number_from + 1 < formGenerateUser.number_to">
              {{formGenerateUser.prefix + (formGenerateUser.number_from + 1) + formGenerateUser.suffix + '...'}}
            </span>
            <span v-if="formGenerateUser.number_from + 1 <= formGenerateUser.number_to">
              {{formGenerateUser.prefix + formGenerateUser.number_to + formGenerateUser.suffix}}
            </span>
          </span>
        </el-form-item>
      </el-form>
    </Panel>
    <!--对话框-->
    <LegacyDialog :title="$t('m.User_Info')" :visible="showUserDialog" @update:visible="showUserDialog = $event" :close-on-click-modal="false">
      <el-form :model="user" label-width="120px" label-position="left">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="$t('m.User_Username')" required>
              <el-input v-model="user.username"></el-input>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('m.User_Real_Name')" required>
              <el-input v-model="user.real_name"></el-input>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('m.User_Email')" required>
              <el-input v-model="user.email"></el-input>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('m.User_New_Password')">
              <el-input v-model="user.password"></el-input>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('m.User_Type')">
              <el-select v-model="user.admin_type">
                <el-option label="普通用户" value="Regular User"></el-option>
                <el-option label="管理员" value="Admin"></el-option>
                <el-option label="超级管理员" value="Super Admin"></el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('m.Problem_Permission')">
              <el-select v-model="user.problem_permission" :disabled="user.admin_type!=='Admin'">
                <el-option label="无权限" value="None"></el-option>
                <el-option label="仅自己创建的题目" value="Own"></el-option>
                <el-option label="全部题目" value="All"></el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('m.Two_Factor_Auth')">
              <el-switch
                v-model="user.two_factor_auth"
                :disabled="!user.real_tfa"
                active-color="#13ce66"
                inactive-color="#ff4949">
              </el-switch>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="开放 API">
              <el-switch
                v-model="user.open_api"
                active-color="#13ce66"
                inactive-color="#ff4949">
              </el-switch>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="$t('m.Is_Disabled')">
              <el-switch
                v-model="user.is_disabled">
              </el-switch>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer><span  class="dialog-footer">
        <cancel @click="showUserDialog = false"></cancel>
        <save @click="saveUser()"></save>
      </span></template>
    </LegacyDialog>
  </div>
</template>
<script>
  import papa from 'papaparse'
  import api from '../../api.js'
  import utils from '@/utils/utils'

  export default {
    name: 'User',
    data () {
      return {
        // 一页显示的用户数
        pageSize: 10,
        // 用户总数
        total: 0,
        // 用户列表
        userList: [],
        uploadUsers: [],
        uploadUsersPage: [],
        uploadUsersCurrentPage: 1,
        uploadUsersPageSize: 15,
        // 搜索关键字
        keyword: '',
        // 是否显示用户对话框
        showUserDialog: false,
        // 当前用户model
        user: {},
        loadingTable: false,
        loadingGenerate: false,
        // 当前页码
        currentPage: 1,
        selectedUsers: [],
        formGenerateUser: {
          prefix: '',
          suffix: '',
          number_from: 0,
          number_to: 0,
          password_length: 8
        }
      }
    },
    mounted () {
      this.getUserList(1)
    },
    methods: {
      // 切换页码回调
      currentChange (page) {
        this.currentPage = page
        this.getUserList(page)
      },
      // 提交修改用户的信息
      saveUser () {
        api.editUser(this.user).then(res => {
          // 更新列表
          this.getUserList(this.currentPage)
        }).then(() => {
          this.showUserDialog = false
        }).catch(() => {
        })
      },
      // 打开用户对话框
      openUserDialog (id) {
        this.showUserDialog = true
        api.getUser(id).then(res => {
          this.user = res.data.data
          this.user.password = ''
          this.user.real_tfa = this.user.two_factor_auth
        })
      },
      // 获取用户列表
      getUserList (page) {
        this.loadingTable = true
        api.getUserList((page - 1) * this.pageSize, this.pageSize, this.keyword).then(res => {
          this.loadingTable = false
          this.total = res.data.data.total
          this.userList = res.data.data.results
        }, res => {
          this.loadingTable = false
        })
      },
      deleteUsers (ids) {
        this.$confirm('确定删除所选用户吗？该用户创建的题目、比赛和公告等资源也会一并删除。', '删除用户', {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        }).then(() => {
          api.deleteUsers(ids.join(',')).then(res => {
            this.getUserList(this.currentPage)
          }).catch(() => {
            this.getUserList(this.currentPage)
          })
        }, () => {
        })
      },
      handleSelectionChange (val) {
        this.selectedUsers = val
      },
      generateUser () {
        this.$refs['formGenerateUser'].validate((valid) => {
          if (!valid) {
            this.$error('请检查生成参数')
            return
          }
          this.loadingGenerate = true
          let data = Object.assign({}, this.formGenerateUser)
          api.generateUser(data).then(res => {
            this.loadingGenerate = false
            let url = '/admin/generate_user?file_id=' + res.data.data.file_id
            utils.downloadFile(url).then(() => {
              this.$alert('用户已全部创建，账号表格已下载。', '生成完成')
            })
            this.getUserList(1)
          }).catch(() => {
            this.loadingGenerate = false
          })
        })
      },
      handleUsersCSV (file) {
        papa.parse(file, {
          complete: (results) => {
            let data = results.data.filter(user => {
              return user[0] && user[1] && user[2] && user[3]
            })
            let delta = results.data.length - data.length
            if (delta > 0) {
              this.$warning(`${delta} 行数据因存在空值而被过滤`)
            }
            this.uploadUsersCurrentPage = 1
            this.uploadUsers = data
            this.uploadUsersPage = data.slice(0, this.uploadUsersPageSize)
          },
          error: (error) => {
            this.$error(error)
          }
        })
      },
      handleUsersUpload () {
        api.importUsers(this.uploadUsers).then(res => {
          this.getUserList(1)
          this.handleResetData()
        }).catch(() => {
        })
      },
      handleResetData () {
        this.uploadUsers = []
      }
    },
    computed: {
      selectedUserIDs () {
        let ids = []
        for (let user of this.selectedUsers) {
          ids.push(user.id)
        }
        return ids
      }
    },
    watch: {
      'keyword' () {
        this.currentChange(1)
      },
      'user.admin_type' () {
        if (this.user.admin_type === 'Super Admin') {
          this.user.problem_permission = 'All'
        } else if (this.user.admin_type === 'Regular User') {
          this.user.problem_permission = 'None'
        }
      },
      'uploadUsersCurrentPage' (page) {
        this.uploadUsersPage = this.uploadUsers.slice((page - 1) * this.uploadUsersPageSize, page * this.uploadUsersPageSize)
      }
    }
  }
</script>

<style scoped lang="less">
  .import-user-icon {
    color: #555555;
    margin-left: 4px;
  }

  .userPreview {
    padding-left: 10px;
  }

  .notification {
    p {
      margin: 0;
      text-align: left;
    }
  }
</style>
