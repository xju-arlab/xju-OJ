<template>
  <el-row type="flex" :gutter="20">
    <el-col :md="10" :lg="8">
      <el-card class="admin-info">
        <el-row :gutter="20">
          <el-col :span="10">
            <UserAvatar class="avatar" :src="profile.avatar" :username="user.username" :size="92" />
          </el-col>
          <el-col :span="14">
            <p class="admin-info-name">{{user.username}}</p>
            <p>{{adminTypeLabel}}</p>
          </el-col>
        </el-row>
        <hr/>
        <div class="last-info">
          <p class="last-info-title">{{$t('m.Last_Login')}}</p>
          <el-form label-width="80px" class="last-info-body">
            <el-form-item label="时间：">
              <span>{{ $filters.localtime(session.last_activity) }}</span>
            </el-form-item>
            <el-form-item label="IP:">
              <span>{{session.ip}}</span>
            </el-form-item>
            <el-form-item label="OS">
              <span>{{os}}</span>
            </el-form-item>
            <el-form-item label="浏览器：">
              <span>{{browser}}</span>
            </el-form-item>
          </el-form>
        </div>
      </el-card>
      <panel :title="$t('m.System_Overview')" v-if="isSuperAdmin">
        <p>{{$t('m.DashBoardJudge_Server')}}:  {{infoData.judge_server_count}}</p>
        <p>{{$t('m.HTTPS_Status')}}:
          <el-tag :type="https ? 'success' : 'danger'" size="small">
            {{ https ? '已启用' : '未启用'}}
          </el-tag>
        </p>
        <p>{{$t('m.Force_HTTPS')}}:
          <el-tag :type="forceHttps ? 'success' : 'danger'" size="small">
            {{forceHttps ? '已启用' : '未启用'}}
          </el-tag>
        </p>
        <p>{{$t('m.CDN_HOST')}}:
          <el-tag :type="cdn ? 'success' : 'warning'" size="small">
            {{cdn ? cdn : '未使用'}}
          </el-tag>
        </p>
      </panel>
    </el-col>

    <el-col :md="14" :lg="16" v-if="isSuperAdmin">
      <div class="info-container">
        <info-card color="#78736a" icon="users" message="用户总数" iconSize="30px" class="info-item"
                   :value="infoData.user_count"></info-card>
        <info-card color="#0f7b6c" icon="bars" message="今日提交" class="info-item"
                   :value="infoData.today_submission_count"></info-card>
        <info-card color="#b7791f" icon="trophy" message="近期比赛" class="info-item"
                   :value="infoData.recent_contest_count"></info-card>
      </div>
      <panel style="margin-top: 5px">
        <template #title><span>XJU-OJ 更新日志</span></template>

        <el-collapse v-model="activeNames" v-for="(release, index) of releases" :key="'release' + index">
          <el-collapse-item :name="index+1">
            <template #title>
              <div v-if="release.current">{{release.title}}
                <el-tag size="small" type="success">当前版本</el-tag>
              </div>
              <span v-else>{{release.title}}</span>
            </template>
            <p class="release-meta">{{release.date}} · {{release.level}}</p>
            <div class="release-body"><ul><li v-for="detail in release.details" :key="detail">{{detail}}</li></ul></div>
          </el-collapse-item>
        </el-collapse>
      </panel>
    </el-col>
  </el-row>
</template>
<script>
  import { mapGetters } from '@/store/compat'
  import browserDetector from 'browser-detect'
  import InfoCard from '@admin/components/infoCard.vue'
  import api from '@admin/api'
  import UserAvatar from '@/shared/ui/UserAvatar.vue'

  export default {
    name: 'dashboard',
    components: {
      InfoCard,
      UserAvatar
    },
    data () {
      return {
        infoData: {
          user_count: 0,
          recent_contest_count: 0,
          today_submission_count: 0,
          judge_server_count: 0,
          env: {}
        },
        activeNames: [1],
        session: {},
        releases: [
          {
            title: '版本 1.0.0 · 三平台远程判题与管理后台完善',
            date: '2026-08',
            level: '当前稳定版本',
            current: true,
            details: [
              '打通牛客、洛谷与 Codeforces 的浏览器远程提交及题目导入链路。',
              '完善比赛报名、远程判题状态、比赛排名和管理员端题目编排。',
              '统一管理后台中文界面、Lucide 图标和危险操作样式。'
            ]
          },
          {
            title: '版本 0.2.0 · 飞跃视觉体系迁移',
            date: '2026-08',
            level: '界面版本',
            current: false,
            details: [
              '使用 XJU-Feiyue 设计体系统一公共 OJ 与管理后台的视觉语言。',
              '完善 Lucide 图标、响应式导航、表格、弹窗和判题状态展示。',
              '升级 Vue 3、Element Plus、Vite 与本地前端开发流程。'
            ]
          },
          {
            title: '版本 0.1.0 · XJU-OJ 平台现代化',
            date: '2026-07',
            level: '基础版本',
            current: false,
            details: [
              '升级应用运行环境、部署流水线和双入口前端构建。',
              '接入 Authentik，收紧 CSRF 边界并实现可复现的容器构建。',
              '在迁移期间保持原有判题、比赛、提交和编辑器能力。'
            ]
          }
        ]
      }
    },
    mounted () {
      api.getDashboardInfo().then(resp => {
        this.infoData = resp.data.data
      }, () => {
      })
      api.getSessions().then(resp => {
        this.parseSession(resp.data.data)
      }, () => {
      })
    },
    methods: {
      parseSession (sessions) {
        let session = sessions[0]
        if (sessions.length > 1) {
          session = sessions.filter(s => !s.current_session).sort((a, b) => {
            return new Date(b.last_activity) - new Date(a.last_activity)
          })[0]
        }
        this.session = session || {}
      }
    },
    computed: {
      ...mapGetters(['profile', 'user', 'isSuperAdmin']),
      adminTypeLabel () {
        return {
          'Regular User': '普通用户',
          'Admin': '管理员',
          'Super Admin': '超级管理员'
        }[this.user.admin_type] || this.user.admin_type
      },
      cdn () {
        return this.infoData.env.STATIC_CDN_HOST
      },
      https () {
        return document.URL.slice(0, 5) === 'https'
      },
      forceHttps () {
        return this.infoData.env.FORCE_HTTPS
      },
      browser () {
        let b = browserDetector(this.session.user_agent)
        if (b.name && b.version) {
          return b.name + ' ' + b.version
        } else {
          return '未知'
        }
      },
      os () {
        let b = browserDetector(this.session.user_agent)
        return b.os ? b.os : '未知'
      }
    }
  }
</script>

<style lang="less">
  .admin-info {
    margin-bottom: 20px;
    &-name {
      font-size: 24px;
      font-weight: 700;
      margin-bottom: 10px;
      color: #409EFF;
    }
    .avatar {
      max-width: 100%;
    }
    .avatar-fallback {
      display: grid;
      width: 92px;
      height: 92px;
      place-items: center;
      border-radius: 50%;
      background: var(--color-bg-subtle);
      color: var(--color-text);
      font-size: 30px;
      font-weight: 700;
    }
    .last-info {
      &-title {
        font-size: 16px;
      }
      &-body {
        .el-form-item {
          margin-bottom: 5px;
        }
      }
    }
  }

  .info-container {
    display: flex;
    justify-content: flex-start;
    flex-wrap: wrap;
    .info-item {
      flex: 1 0 auto;
      min-width: 200px;
      margin-bottom: 10px;
    }
  }

  .release-meta {
    margin: 4px 0 8px;
    color: var(--color-text-faint);
    font-size: 12px;
  }

  .release-body ul {
    margin: 6px 0;
    padding-left: 20px;
  }

</style>
