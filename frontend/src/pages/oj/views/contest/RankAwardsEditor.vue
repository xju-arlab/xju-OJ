<template>
  <div class="rank-awards">
    <el-radio-group v-model="mode" class="rank-awards-mode" size="small" @change="emitChange">
      <el-radio-button value="advance">晋级</el-radio-button>
      <el-radio-button value="medal">奖牌</el-radio-button>
    </el-radio-group>
    <p class="rank-awards-note">
      {{ official ? `正式参赛 ${official} ${unit}（不含打星）` : '正式参赛数按比赛时的榜单计算' }}。每档填个数或百分比，另一项自动换算；按百分比算个数时向下取整。
    </p>
    <table class="rank-awards-table">
      <thead><tr><th></th><th>个数</th><th>百分比</th></tr></thead>
      <tbody>
        <tr v-for="[key, label] in tiers" :key="key">
          <th><span class="rank-awards-tier"><i :class="['rank-tier-mark', `is-${key}`]"></i>{{ label }}</span></th>
          <td :class="{ 'is-auto': rows[key].kind === 'percent' }">
            <el-input-number v-model="rows[key].count" :aria-label="`${label}个数`" :min="0" :max="official || Infinity" :step="1" :precision="0"
                             size="small" controls-position="right" @change="setCount(key, $event)" />
          </td>
          <td :class="{ 'is-auto': rows[key].kind === 'count' }">
            <el-input-number v-model="rows[key].percent" :aria-label="`${label}百分比`" :min="0" :max="100" :step="1" :precision="2"
                             size="small" controls-position="right" @change="setPercent(key, $event)" />
            <span class="rank-awards-unit">%</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="official && total > official" class="rank-awards-note is-warning">各档合计 {{ total }} 名，超过正式参赛数，超出的不标注</p>
  </div>
</template>
<script>
  import { AWARD_MODES, countPercent, percentCount } from '@/utils/rankAwards'

  const emptyRow = () => ({ kind: null, count: null, percent: null })

  export default {
    name: 'RankAwardsEditor',
    props: {
      // Saved rank_awards to start from; empty starts a fresh advancing setting.
      awards: { type: Object, default: () => ({}) },
      // Official places, which percentages count; 0 while not yet known.
      official: { type: Number, default: 0 },
      unit: { type: String, default: '支' }
    },
    // change carries { mode, tiers } as the API takes it, or null while no tier is set.
    emits: ['change'],
    data () {
      return { mode: 'advance', rows: {} }
    },
    computed: {
      tiers () { return AWARD_MODES[this.mode] },
      total () { return this.tiers.reduce((sum, [key]) => sum + (this.rows[key].count || 0), 0) },
      // What the admin typed for each tier; the other figure is only shown.
      payload () {
        const tiers = {}
        for (const [key] of this.tiers) {
          const row = this.rows[key]
          const value = row.kind === 'percent' ? row.percent : row.count
          if (row.kind && value !== null && value !== undefined) tiers[key] = { kind: row.kind, value }
        }
        return Object.keys(tiers).length ? { mode: this.mode, tiers } : null
      }
    },
    watch: {
      awards: { immediate: true, handler: 'load' },
      // Counts follow percentages as the official places change, say with a new roster.
      official () {
        for (const [key, row] of Object.entries(this.rows)) {
          if (row.kind === 'percent') this.setPercent(key, row.percent)
          else if (row.kind === 'count') this.setCount(key, row.count)
        }
      }
    },
    methods: {
      load () {
        const awards = this.awards || {}
        const saved = awards.tiers || {}
        this.mode = AWARD_MODES[awards.mode] ? awards.mode : 'advance'
        const keys = [...AWARD_MODES.advance, ...AWARD_MODES.medal].map(([key]) => key)
        this.rows = Object.fromEntries(keys.map(key => [key, emptyRow()]))
        for (const key of keys) {
          if (saved[key] && saved[key].kind === 'percent') this.setPercent(key, saved[key].value)
          else if (saved[key]) this.setCount(key, saved[key].value)
        }
        this.emitChange()
      },
      setCount (key, count) {
        const empty = count === null || count === undefined
        const percent = empty || !this.official ? null : countPercent(count, this.official)
        Object.assign(this.rows[key], { kind: empty ? null : 'count', count: empty ? null : count, percent })
        this.emitChange()
      },
      setPercent (key, percent) {
        const empty = percent === null || percent === undefined
        const count = empty || !this.official ? null : percentCount(percent, this.official)
        Object.assign(this.rows[key], { kind: empty ? null : 'percent', percent: empty ? null : percent, count })
        this.emitChange()
      },
      emitChange () {
        this.$emit('change', this.payload)
      }
    }
  }
</script>
<style scoped lang="less">
  .rank-awards-mode { margin-bottom: 10px; }
  .rank-awards-note { margin: 0 0 10px; color: var(--color-text-muted); font-size: 12px; line-height: 1.6; }
  .rank-awards-note.is-warning { margin: 8px 0 0; color: #b7791f; }
  .rank-awards-table { border-collapse: collapse; }
  .rank-awards-table th { padding: 4px 8px 4px 0; color: var(--color-text-muted); font-size: 12px; font-weight: 600; text-align: left; }
  .rank-awards-table td { padding: 4px 12px 4px 0; white-space: nowrap; }
  .rank-awards-table :deep(.el-input-number) { width: 120px; }
  // The figure worked out from the other one.
  .rank-awards-table td.is-auto :deep(.el-input__inner) { color: var(--color-text-faint); }
  .rank-awards-unit { margin-left: 6px; color: var(--color-text-muted); font-size: 12px; }
  .rank-awards-tier { display: inline-flex; align-items: center; gap: 6px; color: var(--color-text); font-weight: 500; }
</style>
