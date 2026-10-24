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
          <el-tabs v-model="activeTab" class="profile-tabs">
            <el-tab-pane name="solved" :label="$t('m.Profile_Tab_Solved')">
              <div v-if="refreshVisible" class="profile-tab-tools">
                <Poptip trigger="hover" placement="right-start">
                  <Icon type="ios-help-outline"></Icon>
                  <template #content><div >
                    <p>If you find the following problem id does not exist,<br> try to click the button.</p>
                    <LegacyButton type="info" @click="freshProblemDisplayID">regenerate</LegacyButton>
                  </div></template>
                </Poptip>
              </div>
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
        api.freshDisplayID().then(res => {
          this.$success('Update successfully')
          this.refreshCount += 1
          this.init()
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
      text-align: left;
      .profile-tab-tools { display: flex; justify-content: flex-end; margin-bottom: 4px; color: var(--color-text-faint); }
    }
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
