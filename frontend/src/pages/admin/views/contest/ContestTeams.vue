<template>
  <div class="view">
    <Panel :title="`队伍账号 · ${contest.title || $route.params.contestId}`">
      <section class="team-section">
        <h3>导入队伍</h3>
        <TeamRosterImport ref="roster" :existing-names="teams.map(team => team.name)" @update:teams="roster = $event" />
        <div class="team-actions">
          <el-button type="primary" :loading="generating" :disabled="!roster.length" @click="generate">生成 {{ roster.length || '' }} 个账号</el-button>
          <span class="team-link">比赛链接：<a :href="arenaLink" target="_blank" rel="noopener">{{ arenaLink }}</a></span>
        </div>
      </section>

      <section v-if="created.length" class="team-section is-created">
        <h3>本次生成（密码只在这里给出一次，已自动下载 CSV）</h3>
        <el-table :data="created" size="small">
          <el-table-column prop="name" label="队伍名" />
          <el-table-column label="队员"><template #default="{ row }">{{ row.members.join('、') || '—' }}</template></el-table-column>
          <el-table-column prop="username" label="用户名" width="140" />
          <el-table-column prop="password" label="密码" width="120"><template #default="{ row }"><code>{{ row.password }}</code></template></el-table-column>
        </el-table>
        <el-button class="team-download" @click="download(created)">再次下载账号密码</el-button>
      </section>

      <section class="team-section">
        <h3>已有队伍（{{ teams.length }}）</h3>
        <el-table v-loading="loading" :data="teams" size="small">
          <el-table-column prop="name" label="队伍名" />
          <el-table-column label="队员"><template #default="{ row }">{{ row.members.join('、') || '—' }}</template></el-table-column>
          <el-table-column prop="username" label="用户名" width="140" />
          <el-table-column label="创建时间" width="170"><template #default="{ row }">{{ $filters.localtime(row.create_time) }}</template></el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }"><div class="team-row-actions">
              <icon-btn name="重置密码" icon="ios-locked-outline" @click="resetPassword(row)"></icon-btn>
              <icon-btn danger name="删除" icon="trash" @click="remove(row)"></icon-btn>
            </div></template>
          </el-table-column>
        </el-table>
      </section>
    </Panel>
  </div>
</template>
<script>
  import api from '../../api.js'
  import TeamRosterImport from '@/shared/ui/TeamRosterImport.vue'
  import { downloadTeamAccounts } from '@/utils/teamRoster'

  export default {
    name: 'ContestTeams',
    components: { TeamRosterImport },
    data () {
      return { contest: {}, teams: [], roster: [], created: [], loading: false, generating: false }
    },
    computed: {
      contestId () { return this.$route.params.contestId },
      arenaLink () { return `${window.location.origin}/arena/${this.contestId}` }
    },
    mounted () {
      api.getContest(this.contestId).then(res => { this.contest = res.data.data }, () => {})
      this.load()
    },
    methods: {
      load () {
        this.loading = true
        api.getContestTeams(this.contestId).then(res => { this.teams = res.data.data }, () => {}).finally(() => { this.loading = false })
      },
      download (teams) {
        downloadTeamAccounts(`contest-${this.contestId}-teams.csv`, teams)
      },
      generate () {
        this.generating = true
        api.createContestTeams(this.contestId, this.roster).then(res => {
          this.created = res.data.data
          this.download(this.created)
          this.$refs.roster.reset()
          this.load()
        }, () => {}).finally(() => { this.generating = false })
      },
      resetPassword (team) {
        this.$confirm(`为「${team.name}」生成新密码？旧密码立即失效。`, '重置密码', { confirmButtonText: '重置', cancelButtonText: '取消', type: 'warning' }).then(() => {
          return api.resetContestTeamPassword(this.contestId, team.id).then(res => {
            const item = res.data.data
            this.$alert(`${item.username} 的新密码：${item.password}`, '新密码（只显示一次）', { confirmButtonText: '已记下' })
          })
        }).catch(() => {})
      },
      remove (team) {
        this.$confirm(`删除「${team.name}」的账号？已有提交的队伍不能删除。`, '删除队伍', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }).then(() => {
          return api.deleteContestTeam(this.contestId, team.id).then(() => this.load())
        }).catch(() => {})
      }
    }
  }
</script>
<style scoped lang="less">
  .team-section { padding: 16px 20px; border-bottom: 1px solid var(--color-border); }
  .team-section:last-child { border-bottom: 0; }
  .team-section h3 { margin: 0 0 12px; color: var(--color-text); font-size: 14px; font-weight: 650; }
  .team-section.is-created { background: var(--color-bg-subtle); }
  .team-actions { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-top: 12px; }
  .team-link { color: var(--color-text-muted); font-size: 12px; overflow-wrap: anywhere; }
  .team-link a { font-family: var(--font-mono); }
  .team-download { margin-top: 12px; }
  .team-row-actions { display: flex; align-items: center; }
  code { font-family: var(--font-mono); }
</style>
