<template>
  <header id="header">
    <div class="nav-inner">
      <Menu theme="light" mode="horizontal" @on-select="handleRoute" :active-name="activeMenu" class="oj-menu">
        <div class="logo" aria-label="XJU-OJ"><span class="brand-mark">XJ</span><span class="brand-name">XJU-OJ</span></div>
        <Menu-item name="/"><Icon type="home" />{{$t('m.Home')}}</Menu-item>
        <Menu-item name="/problem" @mouseenter="prefetchRoute('/problem')"><Icon type="ios-keypad" />{{$t('m.NavProblems')}}</Menu-item>
        <Menu-item class="ai-nav-item" name="/ai-studio" @mouseenter="prefetchRoute('/ai-studio')"><Icon type="ios-analytics" />{{$t('m.AI_Studio')}}</Menu-item>
        <Menu-item name="/contest" @mouseenter="prefetchRoute('/contest')"><Icon type="trophy" />{{$t('m.Contests')}}</Menu-item>
        <Menu-item name="/status" @mouseenter="prefetchRoute('/status')"><Icon type="ios-pulse-strong" />{{$t('m.NavStatus')}}</Menu-item>
        <Submenu name="rank" @mouseenter="prefetchRoutes(['/acm-rank', '/oi-rank'])"><template #title><Icon type="podium" />{{$t('m.Rank')}}</template><Menu-item name="/acm-rank">{{$t('m.ACM_Rank')}}</Menu-item><Menu-item name="/oi-rank">{{$t('m.OI_Rank')}}</Menu-item></Submenu>
        <Submenu name="about" @mouseenter="prefetchRoutes(['/about', '/faq', '/remote-bridge'])"><template #title><Icon type="information-circled" />{{$t('m.About')}}</template><Menu-item name="/about">{{$t('m.Judger')}}</Menu-item><Menu-item name="/faq">{{$t('m.FAQ')}}</Menu-item><Menu-item name="/remote-bridge">{{$t('m.Remote_Bridge')}}</Menu-item></Submenu>
      </Menu>
      <div class="nav-actions">
        <div class="nav-search"><Input v-model="searchKeyword" :placeholder="$t('m.Search_Problems')" @on-enter="handleSearch"><template #prefix><Icon type="search" /></template></Input></div>
        <template v-if="!isAuthenticated">
          <LegacyButton type="ghost" ref="loginBtn" :loading="devLoginLoading" @click="handleBtnClick('login')">{{$t('m.Login')}}</LegacyButton>
          <LegacyButton v-if="authentikEnabled" type="ghost" @click="goAuthentikRegister">{{$t('m.Register')}}</LegacyButton>
          <LegacyButton v-else-if="website.allow_register && localRegisterEnabled" type="ghost" @click="handleBtnClick('register')">{{$t('m.Register')}}</LegacyButton>
        </template>
        <Dropdown v-else @on-click="handleRoute" placement="bottom-end" trigger="click">
          <LegacyButton type="text" class="drop-menu-title"><UserAvatar class="user-avatar" :src="profile.avatar" :username="user.username" :size="26" />{{ user.username }} <Icon type="arrow-down-b" /></LegacyButton>
          <template #list><Dropdown-menu><Dropdown-item name="/user-home">{{$t('m.MyHome')}}</Dropdown-item><Dropdown-item name="/status?myself=1">{{$t('m.MySubmissions')}}</Dropdown-item><Dropdown-item name="/setting/profile">{{$t('m.Settings')}}</Dropdown-item><Dropdown-item v-if="isAdminRole" name="/admin">{{$t('m.Management')}}</Dropdown-item><Dropdown-item divided name="/logout">{{$t('m.Logout')}}</Dropdown-item></Dropdown-menu></template>
        </Dropdown>
      </div>
    </div>
    <Modal v-model="modalVisible" :width="400"><template #header><div class="modal-title">{{$t('m.Welcome_to')}} XJU-OJ</div></template><component :is="modalStatus.mode" v-if="modalVisible" /><template #footer><div style="display: none"></div></template></Modal>
  </header>
</template>
<script>
import { mapGetters, mapActions } from '@/store/compat'
import login from '@oj/views/user/Login'
import register from '@oj/views/user/Register'
import api from '@oj/api'
import runtime from '@/utils/runtime'
import UserAvatar from '@/shared/ui/UserAvatar.vue'

const prefetchedRoutes = new Set()

export default {
  components: { login, register, UserAvatar }, data () { return { searchKeyword: '', devLoginLoading: false } }, mounted () { this.getProfile() },
  methods: {
    ...mapActions(['getProfile', 'changeModalStatus']),
    handleRoute (route) { if (route && route.indexOf('admin') < 0) this.$router.push(route); else window.open('/admin/') },
    prefetchRoute (target) {
      if (!target || prefetchedRoutes.has(target)) return
      const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection
      if (connection && (connection.saveData || /(^|-)2g$/.test(connection.effectiveType || ''))) return
      prefetchedRoutes.add(target)
      const matched = this.$router.resolve(target).matched
      for (const record of matched) {
        for (const component of Object.values(record.components || {})) {
          if (typeof component === 'function') Promise.resolve(component()).catch(() => prefetchedRoutes.delete(target))
        }
      }
    },
    prefetchRoutes (targets) { targets.forEach(target => this.prefetchRoute(target)) },
    async handleBtnClick (mode) {
      if (mode === 'login' && runtime.OJ_FRONTEND_DEV_MODE) {
        this.devLoginLoading = true
        try {
          await api.login({ username: runtime.DEV_LOGIN_USERNAME, password: runtime.DEV_LOGIN_PASSWORD })
          await this.getProfile()
          this.$success(this.$t('m.Welcome_back'))
          return
        } catch (_) {
          // Keep a pre-filled local form available if the development account
          // has not been initialized yet or requires TFA.
        } finally {
          this.devLoginLoading = false
        }
      }
      this.changeModalStatus({ visible: true, mode })
    },
    handleSearch () { const keyword = this.searchKeyword.trim(); this.$router.push({ path: '/problem', query: keyword ? { keyword } : {} }) },
    goAuthentikRegister () { const url = this.authProviders.authentik && this.authProviders.authentik.register_url; if (url) window.location.assign(url) }
  },
  computed: {
    ...mapGetters(['website', 'modalStatus', 'user', 'profile', 'isAuthenticated', 'isAdminRole', 'authProviders']),
    authentikEnabled () { return !!(this.authProviders.authentik && this.authProviders.authentik.enabled) },
    localRegisterEnabled () { return !this.authProviders.local || this.authProviders.local.register_enabled !== false },
    activeMenu () {
      const path = this.$route.path
      if (path === '/') return '/'
      if (path === '/acm-rank' || path === '/oi-rank') return 'rank'
      if (path === '/about' || path === '/faq' || path === '/remote-bridge') return 'about'
      return '/' + path.split('/')[1]
    },
    modalVisible: { get () { return this.modalStatus.visible }, set (value) { this.changeModalStatus({ visible: value }) } }
  }
}
</script>
<style lang="less" scoped>
#header { min-width: 320px; position: fixed; inset: 0 0 auto; height: 56px; z-index: 1000; background: var(--color-bg); border-bottom: 1px solid var(--color-border); }
.nav-inner { display: flex; align-items: center; max-width: var(--layout-max-width); height: 56px; margin: 0 auto; padding: 0 var(--layout-gutter); overflow: hidden; box-sizing: border-box; }
.oj-menu { flex: 1; min-width: 0; min-height: 56px; height: 56px; border-right: 0 !important; border-bottom: 0; background: var(--color-bg); overflow: hidden; }
.logo { display: inline-flex; align-items: center; gap: 9px; margin: 0 20px 0 0; height: 56px; font-size: 17px; font-weight: 700; color: var(--color-text); white-space: nowrap; }
.brand-mark { display: inline-grid; width: 30px; height: 30px; place-items: center; border-radius: var(--radius-sm); background: var(--color-text); color: #fff; font-size: 11px; letter-spacing: .06em; }
.nav-actions { display: flex; align-items: center; gap: 6px; flex: none; margin-left: 12px; }
.nav-search { width: 210px; }
.drop-menu-title { display: inline-flex; align-items: center; gap: 7px; color: var(--color-text); }
.user-avatar { font-size: 12px; }
.modal-title { font-size: 18px; font-weight: 600; font-family: var(--font-serif); }
:deep(.el-menu-item), :deep(.el-sub-menu__title) { display: inline-flex; align-items: center; justify-content: flex-start; gap: 6px; height: 36px; line-height: 1; margin: 10px 2px; padding: 0 11px; border-radius: var(--radius-sm); color: var(--color-text-muted); }
:deep(.el-menu-item) { height: 36px !important; margin: 10px 2px !important; line-height: 36px !important; box-sizing: border-box; }
:deep(.el-sub-menu) { height: 56px !important; }
:deep(.el-sub-menu__title) { height: 36px !important; margin: 10px 2px !important; padding: 0 11px !important; line-height: 36px !important; box-sizing: border-box; }
:deep(.legacy-icon) { display: inline-flex; flex: none; width: 16px; height: 16px; align-items: center; justify-content: center; line-height: 1; vertical-align: middle; }
:deep(.legacy-icon svg) { display: block; }
:deep(.el-menu-item:hover), :deep(.el-sub-menu__title:hover), :deep(.el-menu-item.is-active) { background: var(--color-bg-subtle); color: var(--color-text); }
:deep(.el-menu-item.is-active), :deep(.el-sub-menu.is-active > .el-sub-menu__title) { border-bottom: 0 !important; }
:deep(.el-menu--horizontal > .el-menu-item.is-active::after), :deep(.el-menu--horizontal > .el-sub-menu.is-active::after), :deep(.el-menu--horizontal > .el-sub-menu .el-sub-menu__title::after) { display: none !important; }
:deep(.el-sub-menu .el-sub-menu__icon-arrow) { display: none; }
:deep(.el-input__wrapper) { min-height: 34px; }
:deep(.el-button) { min-height: 34px; }
@media (max-width: 1000px) { .nav-search { width: 160px; } }
@media (max-width: 1000px) { :deep(.oj-menu > .el-sub-menu:not(.el-sub-menu__hide-arrow)) { display: none; } }
@media (max-width: 760px) { .nav-inner { padding: 0 14px; } .brand-name { display: none; } .nav-actions { margin-left: 6px; } .nav-search { width: 140px; } .nav-actions > .el-button { padding: 0 8px; } }
@media (max-width: 640px) { :deep(.oj-menu > .el-menu-item:nth-of-type(4)) { display: none; } .nav-search { width: 120px; } }
@media (max-width: 520px) { .nav-search { display: none; } :deep(.oj-menu > .el-menu-item:nth-of-type(3)) { display: none; } }
@media (max-width: 420px) { .nav-actions > .el-button:last-child { display: none; } }
@media (max-width: 360px) { .logo { display: none; } }
@media (max-width: 640px) { :deep(.oj-menu > .ai-nav-item) { display: inline-flex !important; } }
</style>
