<template>
  <div class="team-roster">
    <div class="team-roster-bar">
      <label class="team-roster-pick">
        <input type="file" accept=".csv,text/csv" @change="pick" />
        <span>{{ fileName ? '重新选择' : '选择 CSV' }}</span>
      </label>
      <span class="team-roster-file">{{ fileName || '未选择文件' }}</span>
      <el-checkbox v-if="cells" v-model="skipHeader" @change="parse">首行是表头</el-checkbox>
    </div>
    <ul class="team-roster-hint">
      <li>每行一支队伍，依次为 <code>队伍名,队员1,队员2,队员3,队伍类型,校区</code></li>
      <li>队伍类型填 <code>正式队伍</code> 或 <code>打星队伍</code>；留空或整列不写，都算正式队伍</li>
      <li>校区填 <code>博达校区</code> 或 <code>友好校区</code>（也可写博达、友好），可留空或整列不写</li>
      <li>队员不足三人时留空，逗号照写：<code>xx队,tom,jerry,,</code> 为两人正式队，<code>xx队,tom,,,打星队伍,友好校区</code> 为友好校区一人打星队</li>
      <li>队伍名留空时按队员姓氏取名：<code>,赵一,孙二,,</code> 记为赵孙队</li>
      <li v-if="existingTeams.length">已有的队伍（同名，或未写队名但含其全部队员）不重复建号，只补上缺的队员和校区，账号密码不变</li>
      <li>每支新队伍生成一个 team-xxxx 账号和 8 位密码</li>
    </ul>
    <ul v-if="errors.length" class="team-roster-errors" role="alert">
      <li v-for="error in errors.slice(0, 6)" :key="error">{{ error }}</li>
      <li v-if="errors.length > 6">另有 {{ errors.length - 6 }} 处问题</li>
    </ul>
    <div v-else-if="teams.length" class="team-roster-preview">
      <p v-if="existingCount">新建 {{ teams.length - existingCount }} 支<template v-if="starCount">（打星 {{ starCount }} 支）</template>，补充 {{ plan.update.length }} 支已有队伍<template v-if="existingCount > plan.update.length">，{{ existingCount - plan.update.length }} 支已有队伍无新信息</template></p>
      <p v-else>共 {{ teams.length }} 支队伍<template v-if="starCount">，其中打星 {{ starCount }} 支</template></p>
      <table>
        <thead><tr><th>#</th><th>队伍名</th><th>队员</th><th>类型</th><th>校区</th><th v-if="existingCount">处理</th></tr></thead>
        <tbody>
          <tr v-for="(team, index) in teams" :key="team.line">
            <td>{{ index + 1 }}</td>
            <td>{{ team.name }}<small v-if="team.derived" class="team-roster-derived">按姓氏</small></td>
            <td>{{ team.members.join('、') || '—' }}</td>
            <td :class="{ 'team-roster-star': (team.existing || team).star }">{{ (team.existing || team).star ? '打星' : '正式' }}</td>
            <td>{{ CAMPUSES[team.campus || (team.existing && team.existing.campus)] || '—' }}</td>
            <td v-if="existingCount" :class="['team-roster-action', { 'is-update': team.changes && Object.keys(team.changes).length }]">{{ actionText(team) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<script>
  import { CAMPUSES, looksLikeHeader, parseRoster, readRosterText, rosterErrors, rosterPlan } from '@/utils/teamRoster'

  const CHANGE_LABELS = { members: '队员', campus: '校区' }

  export default {
    name: 'TeamRosterImport',
    props: {
      // Teams the contest already has: { id, name, members, star, campus }.
      existingTeams: { type: Array, default: () => [] }
    },
    // update:teams carries the accounts to create, update:updates the changes to
    // existing teams; both are empty while the roster has problems.
    emits: ['update:teams', 'update:updates'],
    data () {
      return { CAMPUSES, fileName: '', text: '', cells: null, skipHeader: false, teams: [], errors: [] }
    },
    computed: {
      starCount () { return this.teams.filter(team => !team.existing && team.star).length },
      existingCount () { return this.teams.filter(team => team.existing).length },
      plan () { return rosterPlan(this.teams) }
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
        this.teams = parseRoster(this.text, this.skipHeader, this.existingTeams)
        this.errors = this.teams.length ? rosterErrors(this.teams) : ['文件里没有队伍']
        const plan = this.errors.length ? { create: [], update: [] } : this.plan
        this.$emit('update:teams', plan.create)
        this.$emit('update:updates', plan.update)
      },
      actionText (team) {
        if (!team.existing) return '新建'
        const changed = Object.keys(team.changes).map(key => CHANGE_LABELS[key])
        const text = changed.length ? '补充' + changed.join('、') : '已有，无新信息'
        return team.conflicts.length ? `${text}；${team.conflicts.join('、')}不一致，未改` : text
      },
      reset () {
        Object.assign(this, { fileName: '', text: '', cells: null, skipHeader: false, teams: [], errors: [] })
        this.$emit('update:teams', [])
        this.$emit('update:updates', [])
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
  .team-roster-hint { margin: 0; padding-left: 18px; color: var(--color-text-faint); font-size: 12px; line-height: 1.7; }
  .team-roster-hint code { padding: 0 4px; border-radius: 3px; background: var(--color-bg-subtle); color: var(--color-text); font-family: var(--font-mono); white-space: nowrap; }
  .team-roster-errors { margin: 0; padding: 8px 10px 8px 26px; border-radius: var(--radius-sm); background: var(--tag-research-bg); color: var(--oj-danger, #c4554d); font-size: 12px; line-height: 1.6; }
  .team-roster-preview p { margin: 0 0 6px; color: var(--color-text-muted); font-size: 12px; }
  .team-roster-preview { max-height: 220px; overflow: auto; border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 8px 10px; }
  .team-roster-preview table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .team-roster-preview th { color: var(--color-text-muted); font-weight: 600; text-align: left; }
  .team-roster-preview th, .team-roster-preview td { padding: 4px 6px; border-bottom: 1px solid var(--color-border); }
  .team-roster-derived { margin-left: 6px; color: var(--color-text-faint); font-size: 11px; }
  .team-roster-preview td:nth-child(4) { width: 44px; color: var(--color-text-faint); }
  .team-roster-preview td.team-roster-star { color: #b7791f; font-weight: 600; }
  .team-roster-preview td:nth-child(5) { width: 64px; color: var(--color-text-muted); white-space: nowrap; }
  .team-roster-action { color: var(--color-text-faint); white-space: nowrap; }
  .team-roster-action.is-update { color: #2873be; font-weight: 600; }
  .team-roster-preview td:first-child { width: 32px; color: var(--color-text-faint); font-variant-numeric: tabular-nums; }
</style>
