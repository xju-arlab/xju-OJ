<template>
  <div class="oj-shell">
    <NavBar v-if="!contestOnly" v-model:notebook-only="notebookOnly" :show-notebook-mode="isAIProblem" />
    <main :class="['content-app', { 'notebook-only': isAIProblem && notebookOnly, 'contest-only': contestOnly }]">
      <router-view v-slot="{ Component }">
        <transition name="fadeInUp" mode="out-in"><component :is="Component" /></transition>
      </router-view>
      <footer class="footer">
        <p>Powered by XJU-ICTHub · Version 1.0.0</p>
      </footer>
    </main>
    <BackTop />
  </div>
</template>
<script>
import { mapActions, mapGetters, mapState } from '@/store/compat'
import { parseAuthError } from '@oj/authError'
import NavBar from '@oj/components/NavBar.vue'
import { arenaContest, enterArena, leaveArena } from '@/utils/arena'

// Team accounts may open their contest, their submissions and the sign-out page only.
const TEAM_ROUTES = ['submission-details', 'logout', 'contest-arena']

export default {
  name: 'app', components: { NavBar },
  data () { return { authErrorHandled: false, notebookOnly: false, arenaContest: arenaContest() } },
  created () { try { document.body.removeChild(document.getElementById('app-loader')) } catch (e) {} },
  mounted () {
    this.getWebsiteConfig(); this.getAuthProviders(); this.surfaceAuthError()
    // The navbar loads the profile; without it the shell does.
    if (this.contestOnly) this.getProfile().catch(() => {})
  },
  methods: {
    ...mapActions(['getWebsiteConfig', 'getAuthProviders', 'changeDomTitle', 'getProfile']),
    inContest (id) {
      return String(this.$route.params.contestID) === String(id) && this.$route.matched.some(record => record.name === 'contest-details')
    },
    keepTeamInContest () {
      const team = this.profile.team
      // The first navigation may still be resolving when the profile arrives.
      if (!team || !this.$route.matched.length) return
      if (this.inContest(team.contest_id) || TEAM_ROUTES.includes(this.$route.name)) return
      this.$router.replace({ name: 'contest-details', params: { contestID: team.contest_id } })
    },
    surfaceAuthError () {
      // The backend reports OIDC failures with a fixed `auth_error` code. The
      // module only resolves allow-listed codes; unknown values fall back to a
      // generic message and the raw value is never rendered.
      if (this.authErrorHandled) return
      const authError = parseAuthError(this.$route.fullPath)
      if (!authError) return
      this.authErrorHandled = true
      this.$error(this.$t(`m.${authError.key}`))
      if (authError.path !== this.$route.fullPath) this.$router.replace(authError.path)
    }
  },
  computed: {
    ...mapState(['website']),
    ...mapGetters(['profile']),
    isAIProblem () { return this.$route.name === 'ai-problem' },
    contestOnly () {
      return Boolean(this.$route.meta.arena || this.$route.path.startsWith('/arena/') || this.profile.team ||
        (this.arenaContest && this.inContest(this.arenaContest)))
    }
  },
  watch: {
    website () { this.changeDomTitle() },
    '$route' (to) {
      this.changeDomTitle(); this.surfaceAuthError()
      if (to.meta.arena || to.path.startsWith('/arena/')) {
        this.arenaContest = String(to.params.contestID)
        enterArena(this.arenaContest)
      } else if (this.arenaContest && !this.inContest(this.arenaContest) && to.name !== 'submission-details') {
        // Leaving the contest returns to the normal site, practice included.
        this.arenaContest = ''
        leaveArena()
      }
      this.keepTeamInContest()
    },
    'profile.team' () { this.keepTeamInContest() },
    isAIProblem (value) { if (!value) this.notebookOnly = false }
  }
}
</script>
<style lang="less">
.content-app { max-width: var(--layout-max-width); width: 100%; margin: 0 auto; padding: 80px var(--layout-gutter) 0; box-sizing: border-box; }
.footer { margin: 48px auto 18px; padding-top: 18px; border-top: 1px solid var(--color-border); text-align: center; color: var(--color-text-faint); font-size: 12px; }
.footer p { margin: 4px 0; }
.footer a { color: inherit; }
.fadeInUp-enter-active { animation: fadeInUp 220ms ease both; }
.content-app.contest-only { padding-top: 28px; }
@media (max-width: 760px) { .content-app { padding: 72px 14px 0; } .content-app.contest-only { padding-top: 16px; } }
@media (prefers-reduced-motion: reduce) { .fadeInUp-enter-active { animation: none; } }
</style>
