<template>
  <div class="prep-invite-page">
    <section class="prep-invite-card" aria-live="polite">
      <span :class="['invite-mark', `is-${state}`]" aria-hidden="true"><Icon :type="markIcon" /></span>

      <template v-if="state === 'login'">
        <h1>{{ $t('m.Prep_Invite_Title') }}</h1>
        <el-button type="primary" @click="login">{{ $t('m.Prep_Invite_Login') }}</el-button>
      </template>

      <template v-else-if="state === 'joining'">
        <h1>{{ $t('m.Prep_Invite_Joining') }}</h1>
      </template>

      <template v-else-if="state === 'joined'">
        <h1>{{ joined.title }}</h1>
        <span :class="['invite-role', `role-${joined.role.toLowerCase()}`]">{{ $t(`m.Prep_Role_${joined.role}`) }}</span>
        <el-button type="primary" @click="enter">{{ $t('m.Prep_Invite_Enter') }}</el-button>
      </template>

      <template v-else>
        <h1>{{ failure }}</h1>
        <el-button @click="$router.push({ name: 'contest-list' })">{{ $t('m.Contests') }}</el-button>
      </template>
    </section>
  </div>
</template>

<script>
import api from '@oj/api'
import { mapGetters, mapActions } from '@/store/compat'
import { forgetInvite, keepPendingInvite, readInviteToken } from './prepInvite'

export default {
  name: 'PrepInvite',
  data () {
    return {
      token: '',
      state: 'joining',
      joined: null,
      failure: ''
    }
  },
  computed: {
    ...mapGetters(['isAuthenticated']),
    markIcon () {
      if (this.state === 'joined') return 'check'
      if (this.state === 'failed') return 'close'
      return 'link'
    }
  },
  watch: {
    isAuthenticated (value) {
      if (value && this.state === 'login') this.accept()
    }
  },
  mounted () {
    this.token = readInviteToken()
    if (!this.token) return this.fail(this.$t('m.Prep_Invite_Invalid'))
    if (this.isAuthenticated) this.accept()
    else this.state = 'login'
  },
  methods: {
    ...mapActions(['changeModalStatus']),
    login () {
      // Keep the token in this tab while the visitor signs in (also through Authentik).
      keepPendingInvite(this.token)
      this.changeModalStatus({ mode: 'login', visible: true })
    },
    fail (message) {
      forgetInvite()
      this.failure = message
      this.state = 'failed'
    },
    async accept () {
      this.state = 'joining'
      try {
        const res = await api.acceptPrepInvite(this.token)
        forgetInvite()
        this.joined = res.data.data
        this.state = 'joined'
      } catch (res) {
        const message = res && res.data && res.data.data
        if (message === 'You are already a member of this contest') return this.fail(this.$t('m.Prep_Invite_Member'))
        if (message === 'Please login first.') {
          this.state = 'login'
          return
        }
        this.fail(this.$t('m.Prep_Invite_Invalid'))
      }
    },
    enter () {
      this.$router.push({ name: 'contest-details', params: { contestID: this.joined.contest_id } })
    }
  }
}
</script>

<style scoped lang="less">
.prep-invite-page {
  display: flex;
  min-height: calc(100vh - 220px);
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
}
.prep-invite-card {
  display: flex;
  width: min(420px, 100%);
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 36px 28px 30px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg);
  text-align: center;
  h1 { margin: 0; color: var(--color-text); font-size: 18px; font-weight: 650; line-height: 1.45; }
  .el-button { min-width: 140px; margin-top: 6px; }
}
.invite-mark {
  display: inline-flex;
  width: 44px;
  height: 44px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--tag-kaggle-bg);
  color: var(--cat-kaggle);
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 20px; height: 20px; }
  &.is-joined { background: var(--tag-tools-bg); color: var(--cat-tools); }
  &.is-failed { background: var(--tag-research-bg); color: var(--cat-research); }
  &.is-joining :deep(svg) { animation: invite-pulse 1.2s ease-in-out infinite; }
}
.invite-role {
  display: inline-flex;
  height: 24px;
  align-items: center;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}
.role-setter { background: var(--tag-course-bg); color: var(--cat-course); }
.role-verifier { background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
@keyframes invite-pulse { 50% { opacity: .45; } }
@media (prefers-reduced-motion: reduce) {
  .invite-mark.is-joining :deep(svg) { animation: none; }
}
</style>
