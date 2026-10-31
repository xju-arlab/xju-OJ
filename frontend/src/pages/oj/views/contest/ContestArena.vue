<template>
  <section class="contest-arena">
    <div class="contest-arena-card">
      <p class="contest-arena-eyebrow">{{ $t('m.Contests') }} / {{ contestID }}</p>
      <h1>{{ contest ? contest.title : '比赛' }}</h1>
      <p v-if="contest" class="contest-arena-time">{{ formatTime(contest.start_time) }} — {{ formatTime(contest.end_time) }}</p>
      <p v-if="contest && contest.status === '1'" class="contest-arena-notice">未到开赛时间，{{ formatTime(contest.start_time) }} 开赛</p>
      <p v-if="error" role="alert" class="contest-arena-error">{{ error }}</p>
      <form v-else-if="mode === 'login'" class="contest-arena-form" @submit.prevent="login">
        <label>队伍账号<el-input v-model="username" placeholder="team-xxxx" autocomplete="username" /></label>
        <label>密码<el-input v-model="password" type="password" show-password autocomplete="current-password" /></label>
        <el-button type="primary" native-type="submit" :loading="loading" :disabled="!username || !password">登录并进入比赛</el-button>
        <p class="contest-arena-hint">使用发放的队伍账号和密码登录，无需统一身份认证。</p>
      </form>
      <div v-else-if="mode === 'other'" class="contest-arena-form">
        <p class="contest-arena-hint">本场比赛只对队伍账号开放，当前登录的是 {{ user.username }}。</p>
        <el-button @click="logout">退出后用队伍账号登录</el-button>
      </div>
      <p v-else class="contest-arena-hint">{{ $t('m.Loading') }}</p>
    </div>
  </section>
</template>
<script>
  import moment from 'moment'
  import { mapGetters } from '@/store/compat'
  import api from '@oj/api'

  export default {
    name: 'ContestArena',
    data () {
      return { contest: null, mode: '', error: '', username: '', password: '', loading: false }
    },
    computed: {
      ...mapGetters(['profile', 'user', 'isAuthenticated']),
      contestID () { return String(this.$route.params.contestID) }
    },
    async mounted () {
      try {
        this.contest = (await api.getContest(this.contestID)).data.data
      } catch (_) {
        this.error = '比赛不存在'
        return
      }
      try { await this.$store.dispatch('getProfile') } catch (_) {}
      this.route()
    },
    methods: {
      formatTime (value) { return moment(value).format('YYYY-MM-DD HH:mm') },
      enter () { this.$router.replace({ name: 'contest-details', params: { contestID: this.contestID } }) },
      route () {
        const team = this.profile.team
        // Once the contest is over its pages are open to everyone, read only.
        if (this.contest.status === '-1') return this.enter()
        if (team && String(team.contest_id) === this.contestID) return this.enter()
        if (team) return
        if (!this.isAuthenticated) { this.mode = 'login'; return }
        const admin = this.contest.created_by.id === this.user.id || this.user.admin_type === 'Super Admin'
        if (admin) return this.enter()
        this.mode = 'other'
      },
      async login () {
        this.loading = true
        try {
          await api.login({ username: this.username.trim(), password: this.password })
          await this.$store.dispatch('getProfile')
          this.route()
        } catch (_) {
          // The API client already shows the error.
        } finally {
          this.loading = false
        }
      },
      async logout () {
        try { await api.logout() } catch (_) {}
        this.$store.dispatch('clearProfile')
        this.mode = 'login'
      }
    }
  }
</script>
<style scoped lang="less">
  .contest-arena { display: flex; min-height: calc(100vh - 160px); align-items: center; justify-content: center; }
  .contest-arena-card { width: min(420px, 100%); padding: 28px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg); }
  .contest-arena-eyebrow { margin: 0; color: var(--color-text-faint); font-size: 12px; }
  .contest-arena-card h1 { margin: 6px 0 4px; color: var(--color-text); font-size: 22px; font-weight: 680; }
  .contest-arena-time { margin: 0 0 20px; color: var(--color-text-muted); font: 12px var(--font-mono); }
  .contest-arena-notice { margin: -8px 0 18px; padding: 8px 10px; border-radius: var(--radius-sm); background: var(--color-bg-subtle); color: var(--color-text); font-size: 13px; }
  .contest-arena-form { display: grid; gap: 14px; }
  .contest-arena-form label { display: grid; gap: 6px; color: var(--color-text-muted); font-size: 12px; font-weight: 600; }
  .contest-arena-hint { margin: 0; color: var(--color-text-faint); font-size: 12px; line-height: 1.6; }
  .contest-arena-error { margin: 0; color: var(--oj-danger, #c4554d); font-size: 13px; }
</style>
