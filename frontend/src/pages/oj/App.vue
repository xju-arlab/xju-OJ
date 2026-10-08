<template>
  <div class="oj-shell">
    <NavBar v-model:notebook-only="notebookOnly" :show-notebook-mode="isAIProblem" />
    <main :class="['content-app', { 'notebook-only': isAIProblem && notebookOnly }]">
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
import { mapActions, mapState } from '@/store/compat'
import { parseAuthError } from '@oj/authError'
import NavBar from '@oj/components/NavBar.vue'
export default {
  name: 'app', components: { NavBar },
  data () { return { authErrorHandled: false, notebookOnly: false } },
  created () { try { document.body.removeChild(document.getElementById('app-loader')) } catch (e) {} },
  mounted () { this.getWebsiteConfig(); this.getAuthProviders(); this.surfaceAuthError() },
  methods: {
    ...mapActions(['getWebsiteConfig', 'getAuthProviders', 'changeDomTitle']),
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
  computed: { ...mapState(['website']), isAIProblem () { return this.$route.name === 'ai-problem' } },
  watch: {
    website () { this.changeDomTitle() },
    '$route' () { this.changeDomTitle(); this.surfaceAuthError() },
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
@media (max-width: 760px) { .content-app { padding: 72px 14px 0; } }
@media (prefers-reduced-motion: reduce) { .fadeInUp-enter-active { animation: none; } }
</style>
