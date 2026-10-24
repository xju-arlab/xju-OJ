<template>
  <div class="container">
    <div class="avatar-container">
      <UserAvatar class="avatar" :src="profile.avatar" :username="profile.user?.username" :size="140" />
    </div>
    <Card :padding="100">
      <div v-if="profile.user">
        <p style="margin-top: -10px">
          <span v-if="profile.user" class="emphasis">{{profile.user.username}}</span>
          <span v-if="profile.school">@{{profile.school}}</span>
        </p>
        <p v-if="profile.mood">
          {{profile.mood}}
        </p>
        <hr id="split"/>

        <div class="flex-container">
          <div class="left">
            <p>{{$t('m.UserHomeSolved')}}</p>
            <p class="emphasis">{{profile.accepted_number}}</p>
          </div>
          <div class="middle">
            <p>{{$t('m.UserHomeserSubmissions')}}</p>
            <p class="emphasis">{{profile.submission_number}}</p>
          </div>
          <div class="right">
            <p>{{$t('m.UserHomeScore')}}</p>
            <p class="emphasis">{{profile.total_score}}</p>
          </div>
        </div>
        <div id="problems">
          <button v-if="refreshVisible && activeTab === 'solved'"
                  type="button"
                  class="profile-refresh"
                  :disabled="refreshing"
                  @click="freshProblemDisplayID">
            <Icon :type="refreshing ? 'loading' : 'refresh'" :class="{ 'is-spinning': refreshing }" />
            <span>{{ $t('m.Profile_Refresh_IDs') }}</span>
          </button>
          <el-tabs v-model="activeTab" class="profile-tabs">
            <el-tab-pane name="solved" :label="$t('m.Profile_Tab_Solved')">
              <ProfileProblemList :key="`solved-${profileKey}`" type="solved" :username="username"
                                  :empty-text="$t('m.UserHomeIntro')" />
            </el-tab-pane>
            <el-tab-pane name="uploaded" :label="$t('m.Profile_Tab_Uploaded')" lazy>
              <ProfileProblemList :key="`uploaded-${profileKey}`" type="uploaded" :username="username"
                                  :empty-text="$t('m.Profile_No_Uploaded')" />
            </el-tab-pane>
            <el-tab-pane v-if="isOwnProfile" name="favorites" :label="$t('m.Profile_Tab_Favorites')" lazy>
              <ProfileProblemList :key="`favorites-${profileKey}`" type="favorites"
                                  :empty-text="$t('m.Profile_No_Favorites')" />
            </el-tab-pane>
          </el-tabs>
        </div>
        <div id="icons">
          <a :href="profile.github">
            <Icon type="social-github-outline" size="30"></Icon>
          </a>
          <a :href="'mailto:'+ profile.user.email">
            <Icon class="icon" type="ios-email-outline" size="30"></Icon>
          </a>
          <a :href="profile.blog">
            <Icon class="icon" type="ios-world-outline" size="30"></Icon>
          </a>
        </div>
      </div>
    </Card>
  </div>
</template>
<script>
  import { mapActions } from '@/store/compat'
  import time from '@/utils/time'
  import api from '@oj/api'
  import UserAvatar from '@/shared/ui/UserAvatar.vue'
  import ProfileProblemList from './ProfileProblemList.vue'

  export default {
    components: {
      UserAvatar,
      ProfileProblemList
    },
    data () {
      return {
        username: '',
        profile: {},
        activeTab: 'solved',
        refreshing: false,
        // Bumped after the display IDs are regenerated so the lists reload.
        refreshCount: 0
      }
    },
    mounted () {
      this.init()
    },
    methods: {
      ...mapActions(['changeDomTitle']),
      init () {
        this.username = this.$route.query.username
        api.getUserInfo(this.username).then(res => {
          this.changeDomTitle({title: res.data.data.user.username})
          this.profile = res.data.data
          if (this.activeTab === 'favorites' && !this.isOwnProfile) this.activeTab = 'solved'
          let registerTime = time.utcToLocal(this.profile.user.create_time, 'YYYY-MM-D')
          console.log('The guy registered at ' + registerTime + '.')
        })
      },
      freshProblemDisplayID () {
        this.refreshing = true
        api.freshDisplayID().then(res => {
          this.$success(this.$t('m.Profile_Refreshed'))
          this.refreshCount += 1
          this.init()
        }).catch(() => {}).finally(() => {
          this.refreshing = false
        })
      }
    },
    computed: {
      refreshVisible () {
        return this.isOwnProfile
      },
      isOwnProfile () {
        if (!this.username) return true
        return this.username === this.$store.getters.user.username
      },
      profileKey () {
        return `${this.username || 'me'}-${this.refreshCount}`
      }
    },
    watch: {
      '$route' (newVal, oldVal) {
        if (newVal !== oldVal) {
          this.init()
        }
      }
    }
  }
</script>

<style lang="less" scoped>
  .container {
    position: relative;
    width: 75%;
    margin: 170px auto;
    text-align: center;
    p {
      margin-top: 8px;
      margin-bottom: 8px;
    }
    .avatar-container {
      position: absolute;
      left: 50%;
      transform: translate(-50%);
      z-index: 1;
      top: -90px;
      .avatar {
        width: 140px;
        height: 140px;
        border-radius: 50%;
        box-shadow: var(--shadow-card);
      }
    }
    .emphasis {
      font-size: 20px;
      font-weight: 600;
    }
    #split {
      margin: 20px auto;
      width: 90%;
    }
    .flex-container {
      margin-top: 30px;
      padding: auto 20px;
      .left {
        flex: 1 1;
      }
      .middle {
        flex: 1 1;
        border-left: 1px solid #999;
        border-right: 1px solid #999;
      }
      .right {
        flex: 1 1;
      }
    }
    #problems {
      margin-top: 40px;
      padding-left: 30px;
      padding-right: 30px;
      position: relative;
      text-align: left;
    }
    // Sits at the right end of the tab bar, level with the tabs.
    .profile-refresh {
      position: absolute;
      z-index: 1;
      top: 4px;
      right: 30px;
      display: inline-flex;
      height: 30px;
      align-items: center;
      gap: 6px;
      padding: 0 12px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background: var(--color-bg);
      color: var(--color-text-muted);
      font: inherit;
      font-size: 13px;
      cursor: pointer;
      transition: background-color var(--transition), border-color var(--transition), color var(--transition);
      :deep(.legacy-icon) { display: inline-flex; }
      :deep(svg) { width: 14px; height: 14px; }
      &:hover:not(:disabled), &:focus-visible { border-color: var(--line-strong); background: var(--color-bg-subtle); color: var(--color-text); }
      &:focus { outline: none; }
      &:focus-visible { box-shadow: 0 0 0 2px rgba(35, 131, 226, .25); }
      &:disabled { cursor: wait; color: var(--color-text-faint); }
      .is-spinning { animation: profile-spin 1s linear infinite; }
    }
    @keyframes profile-spin { to { transform: rotate(360deg); } }
    #icons {
      position: absolute;
      bottom: 20px;
      left: 50%;
      transform: translate(-50%);
      .icon {
        padding-left: 20px;
      }
    }
  }
</style>
