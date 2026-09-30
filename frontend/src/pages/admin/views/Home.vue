<template>
  <div class="container">
    <div>
      <SideMenu></SideMenu>
    </div>
    <div id="header">
      <div class="header-actions">
        <el-tooltip content="LaTeX 公式编辑器" placement="bottom">
          <button type="button" class="admin-icon-button katex-editor" aria-label="LaTeX 公式编辑器" @click="katexVisible=true">
            <Icon type="file-text" />
          </button>
        </el-tooltip>
        <el-dropdown @command="handleCommand">
          <button type="button" class="admin-user" aria-label="用户菜单">
            <UserAvatar class="user-avatar" :src="profile.avatar" :username="user.username" :size="26" />
            <span>{{user.username}}</span>
            <Icon type="arrow-down-b" />
          </button>
          <template #dropdown><el-dropdown-menu >
            <el-dropdown-item command="logout">退出登录</el-dropdown-item>
          </el-dropdown-menu></template>
        </el-dropdown>
      </div>
    </div>
    <div class="content-app">
      <router-view v-slot="{ Component }">
        <transition name="fadeInUp" mode="out-in">
          <component :is="Component"></component>
        </transition>
      </router-view>
      <div class="footer">
        由 XJU-ICTHub 提供支持 · 版本 1.0.0
      </div>
    </div>

    <LegacyDialog :title="$t('m.Latex_Editor')" :visible="katexVisible" @update:visible="katexVisible = $event">
      <KatexEditor></KatexEditor>
    </LegacyDialog>
  </div>
</template>
<script>
  import store, { types } from '@/store'
  import { mapGetters } from '@/store/compat'
  import SideMenu from '../components/SideMenu.vue'
  import KatexEditor from '@admin/components/KatexEditor.vue'
  import api from '../api'
  import i18n from '@/i18n'
  import UserAvatar from '@/shared/ui/UserAvatar.vue'

  export default {
    name: 'app',
    data () {
      return {
        version: process.env.VERSION,
        katexVisible: false
      }
    },
    components: {
      SideMenu,
      KatexEditor,
      UserAvatar
    },
    async beforeRouteEnter () {
      const res = await api.getProfile()
      if (!res.data.data) return {name: 'login'}
      store.commit(types.CHANGE_PROFILE, {profile: res.data.data})
      i18n.global.locale.value = 'zh-CN'
    },
    methods: {
      handleCommand (command) {
        if (command === 'logout') {
          api.logout().then(() => {
            store.dispatch('clearProfile')
            this.$router.push({name: 'login'})
          })
        }
      }
    },
    computed: {
      ...mapGetters(['user', 'profile'])
    }
  }
</script>

<style lang="less">
  a {
    background-color: transparent;
  }

  a:active, a:hover {
    outline-width: 0
  }

  img {
    border-style: none
  }

  .container {
    overflow: auto;
    font-weight: 400;
    height: 100%;
    -webkit-font-smoothing: antialiased;
    background-color: var(--color-bg);
    overflow-y: auto;
    min-width: 760px;
  }

  * {
    box-sizing: border-box;
  }

  #header {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding-left: 210px;
    padding-right: 30px;
    height: 50px;
    background: var(--color-bg);
    border-bottom: 1px solid var(--color-border);
  }

  .content-app {
    padding-top: 20px;
    padding-right: 10px;
    padding-left: 210px;
  }

  .footer {
    margin: 15px;
    text-align: center;
    font-size: small;
  }

  @keyframes fadeInUp {
    from {
      opacity: 0;
      transform: translateY(6px);
    }

    to {
      opacity: 1;
      transform: none;
    }
  }

  .fadeInUp-enter-active {
    animation: fadeInUp 220ms ease both;
  }

  .header-actions { display: inline-flex; align-items: center; gap: 10px; height: 100%; }
  .admin-icon-button { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--color-text-muted); cursor: pointer; transition: color var(--transition), background-color var(--transition), border-color var(--transition); }
  .admin-icon-button:hover { color: var(--color-text); background: var(--color-bg-subtle); border-color: var(--color-border); }
  .admin-user { display: inline-flex; align-items: center; gap: 7px; height: 36px; padding: 0 8px; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--color-text); cursor: pointer; transition: color var(--transition), background-color var(--transition), border-color var(--transition); }
  .admin-user:hover { background: var(--color-bg-subtle); border-color: var(--color-border); }
  .user-avatar { font-size: 12px; }
  @media (max-width: 760px) { .container { min-width: 0; } #header { padding-left: 180px; padding-right: 14px; } .content-app { padding-left: 180px; } }



</style>
