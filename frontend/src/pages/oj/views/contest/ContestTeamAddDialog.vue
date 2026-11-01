<template>
  <LegacyDialog title="添加队伍" width="600px" :visible="visible" @update:visible="$emit('update:visible', $event)">
    <template v-if="!created.length">
      <el-radio-group v-model="mode" class="team-add-mode" size="small">
        <el-radio-button value="one">单个添加</el-radio-button>
        <el-radio-button value="csv">批量导入</el-radio-button>
      </el-radio-group>
      <el-form v-if="mode === 'one'" label-position="top" class="team-add-form" @submit.prevent>
        <el-form-item label="队伍类型">
          <el-radio-group v-model="form.star">
            <el-radio :value="false">正式队伍</el-radio>
            <el-radio :value="true">打星队伍</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="队名" :error="nameError">
          <el-input v-model="form.name" :maxlength="TEAM_NAME_MAX" placeholder="留空则按队员姓氏取名" />
        </el-form-item>
        <el-form-item label="队员真实姓名">
          <div class="team-add-members">
            <el-input v-for="index in 3" :key="index" v-model="form.members[index - 1]" :maxlength="MEMBER_NAME_MAX" :placeholder="`队员 ${index}`" />
          </div>
        </el-form-item>
      </el-form>
      <TeamRosterImport v-else ref="roster" :existing-names="existingNames" @update:teams="roster = $event" />
    </template>
    <template v-else>
      <p class="team-add-copy is-warning">密码只在这里给出一次，已自动下载 CSV；可导出 A4 账号条 PDF。登录链接 <a :href="link" target="_blank" rel="noopener">{{ link }}</a></p>
      <el-table :data="created" size="small" max-height="320">
        <el-table-column prop="name" label="队伍名" min-width="120" />
        <el-table-column label="类型" width="64"><template #default="{ row }">{{ row.star ? '打星' : '正式' }}</template></el-table-column>
        <el-table-column label="队员" min-width="120"><template #default="{ row }">{{ row.members.join('、') || '—' }}</template></el-table-column>
        <el-table-column prop="username" label="用户名" width="104" />
        <el-table-column label="密码" width="96"><template #default="{ row }"><code>{{ row.password }}</code></template></el-table-column>
      </el-table>
    </template>
    <template #footer>
      <template v-if="!created.length">
        <el-button @click="$emit('update:visible', false)">{{ $t('m.Cancel') }}</el-button>
        <el-button type="primary" :loading="saving" :disabled="!pending.length" @click="save">生成 {{ pending.length || '' }} 个账号</el-button>
      </template>
      <template v-else>
        <el-button @click="downloadAccounts">再次下载账号密码</el-button>
        <el-button :loading="sheetLoading" @click="downloadSheet">导出 PDF</el-button>
        <el-button type="primary" @click="$emit('update:visible', false)">完成</el-button>
      </template>
    </template>
  </LegacyDialog>
</template>
<script>
  import api from '@oj/api'
  import TeamRosterImport from '@/shared/ui/TeamRosterImport.vue'
  import { MEMBER_NAME_MAX, TEAM_NAME_MAX, downloadTeamAccounts, downloadTeamSheet, surnameTeamName } from '@/utils/teamRoster'

  const emptyForm = () => ({ star: false, name: '', members: ['', '', ''] })

  export default {
    name: 'ContestTeamAddDialog',
    components: { TeamRosterImport },
    props: {
      visible: { type: Boolean, default: false },
      contestId: { type: [String, Number], required: true }
    },
    // created carries the new accounts, so the board can refresh.
    emits: ['update:visible', 'created'],
    data () {
      return { TEAM_NAME_MAX, MEMBER_NAME_MAX, mode: 'one', form: emptyForm(), roster: [], existingNames: [], created: [], saving: false, sheetLoading: false }
    },
    computed: {
      link () { return `${window.location.origin}/arena/${this.contestId}` },
      members () { return this.form.members.map(member => member.trim()).filter(Boolean) },
      // Names are unique within a contest; a blank one comes from the surnames.
      oneName () {
        const name = this.form.name.trim()
        return name || (this.members.length ? surnameTeamName(this.members, new Set(this.existingNames)) : '')
      },
      nameError () {
        return this.existingNames.includes(this.form.name.trim()) ? '本场比赛已有同名队伍' : ''
      },
      pending () {
        if (this.mode === 'csv') return this.roster
        if (!this.oneName || this.nameError) return []
        return [{ name: this.oneName, members: this.members, star: this.form.star }]
      }
    },
    watch: {
      visible (open) {
        if (!open) return
        Object.assign(this, { mode: 'one', form: emptyForm(), roster: [], created: [] })
        this.loadNames()
      }
    },
    methods: {
      loadNames () {
        api.getContestTeams(this.contestId).then(res => { this.existingNames = res.data.data.map(team => team.name) }, () => {})
      },
      async save () {
        this.saving = true
        try {
          this.created = (await api.createContestTeams(this.contestId, this.pending)).data.data
          this.downloadAccounts()
          this.$emit('created', this.created)
        } catch (_) {
          // The API client already shows the error; a name taken meanwhile shows up on reload.
          this.loadNames()
        } finally {
          this.saving = false
        }
      },
      downloadAccounts () {
        downloadTeamAccounts(`contest-${this.contestId}-teams-added.csv`, this.created)
      },
      async downloadSheet () {
        this.sheetLoading = true
        try { await downloadTeamSheet(this.contestId, this.link, this.created) } catch (error) { this.$error(error.message || '导出 PDF 失败') } finally { this.sheetLoading = false }
      }
    }
  }
</script>
<style scoped lang="less">
  .team-add-mode { margin-bottom: 16px; }
  .team-add-form :deep(.el-form-item) { margin-bottom: 14px; }
  .team-add-members { display: grid; width: 100%; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .team-add-copy { margin: 0 0 10px; color: var(--color-text); font-size: 13px; font-weight: 600; line-height: 1.6; }
  .team-add-copy a { font: 12px var(--font-mono); overflow-wrap: anywhere; }
  code { font-family: var(--font-mono); }

  @media (max-width: 560px) {
    .team-add-members { grid-template-columns: 1fr; }
  }
</style>
