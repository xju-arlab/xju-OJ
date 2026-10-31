<template>
  <div class="team-roster">
    <div class="team-roster-bar">
      <label class="team-roster-pick">
        <input type="file" accept=".csv,text/csv" @change="pick" />
        <span>{{ fileName ? '重新选择' : '选择 CSV' }}</span>
      </label>
      <span class="team-roster-file">{{ fileName || '每行一支队伍：队伍名,队员1,队员2,队员3' }}</span>
      <el-checkbox v-if="cells" v-model="skipHeader" @change="parse">首行是表头</el-checkbox>
    </div>
    <p class="team-roster-hint">队员不足三人时后面留空，逗号照写，例如 <code>xx队,tom,,</code> 或 <code>xx队,tom,jerry,</code>；队伍名留空时按队员姓氏取名，例如 <code>,赵一,孙二,</code> 记为赵孙队。每支队伍生成一个 team-xxxx 账号和 8 位密码。</p>
    <ul v-if="errors.length" class="team-roster-errors" role="alert">
      <li v-for="error in errors.slice(0, 6)" :key="error">{{ error }}</li>
      <li v-if="errors.length > 6">另有 {{ errors.length - 6 }} 处问题</li>
    </ul>
    <div v-else-if="teams.length" class="team-roster-preview">
      <p>共 {{ teams.length }} 支队伍</p>
      <table>
        <thead><tr><th>#</th><th>队伍名</th><th>队员</th></tr></thead>
        <tbody>
          <tr v-for="(team, index) in teams" :key="team.line"><td>{{ index + 1 }}</td><td>{{ team.name }}<small v-if="team.derived" class="team-roster-derived">按姓氏</small></td><td>{{ team.members.join('、') || '—' }}</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<script>
  import { looksLikeHeader, parseRoster, readRosterText, rosterErrors } from '@/utils/teamRoster'

  export default {
    name: 'TeamRosterImport',
    props: {
      // Team names the contest already has.
      existingNames: { type: Array, default: () => [] }
    },
    // Emits the parsed roster, or an empty list while it has problems.
    emits: ['update:teams'],
    data () {
      return { fileName: '', text: '', cells: null, skipHeader: false, teams: [], errors: [] }
    },
    methods: {
      async pick (event) {
        const file = event.target.files && event.target.files[0]
        event.target.value = ''
        if (!file) return
        this.fileName = file.name
        this.text = await readRosterText(file)
        const first = parseRoster(this.text, false)[0]
        this.cells = first ? [first.name, ...first.members] : []
        this.skipHeader = looksLikeHeader(this.cells)
        this.parse()
      },
      parse () {
        this.teams = parseRoster(this.text, this.skipHeader, this.existingNames)
        this.errors = this.teams.length ? rosterErrors(this.teams, this.existingNames) : ['文件里没有队伍']
        this.$emit('update:teams', this.errors.length ? [] : this.teams.map(({ name, members }) => ({ name, members })))
      },
      reset () {
        Object.assign(this, { fileName: '', text: '', cells: null, skipHeader: false, teams: [], errors: [] })
        this.$emit('update:teams', [])
      }
    }
  }
</script>
<style scoped lang="less">
  .team-roster { display: grid; gap: 8px; }
  .team-roster-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .team-roster-pick { position: relative; display: inline-flex; min-height: 30px; align-items: center; padding: 0 12px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--color-bg); color: var(--color-text); font-size: 13px; cursor: pointer; }
  .team-roster-pick:hover { background: var(--color-bg-subtle); }
  .team-roster-pick input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  .team-roster-file { min-width: 0; color: var(--color-text-muted); font-size: 12px; overflow-wrap: anywhere; }
  .team-roster-hint { margin: 0; color: var(--color-text-faint); font-size: 12px; line-height: 1.5; }
  .team-roster-hint code { padding: 0 4px; border-radius: 3px; background: var(--color-bg-subtle); color: var(--color-text); font-family: var(--font-mono); }
  .team-roster-errors { margin: 0; padding: 8px 10px 8px 26px; border-radius: var(--radius-sm); background: var(--tag-research-bg); color: var(--oj-danger, #c4554d); font-size: 12px; line-height: 1.6; }
  .team-roster-preview p { margin: 0 0 6px; color: var(--color-text-muted); font-size: 12px; }
  .team-roster-preview { max-height: 220px; overflow: auto; border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 8px 10px; }
  .team-roster-preview table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .team-roster-preview th { color: var(--color-text-muted); font-weight: 600; text-align: left; }
  .team-roster-preview th, .team-roster-preview td { padding: 4px 6px; border-bottom: 1px solid var(--color-border); }
  .team-roster-derived { margin-left: 6px; color: var(--color-text-faint); font-size: 11px; }
  .team-roster-preview td:first-child { width: 32px; color: var(--color-text-faint); font-variant-numeric: tabular-nums; }
</style>
