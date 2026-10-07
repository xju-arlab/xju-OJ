<template>
  <div class="setting-main">
    <div v-if="authentikEnabled" class="identity-card">
      <div>
        <div class="identity-eyebrow">AUTHENTIK</div>
        <div class="identity-title">{{$t('m.Authentik_Account_Notice')}}</div>
      </div>
      <LegacyButton v-if="!authentikLinked" type="primary" @click="bindAuthentik">
        {{$t('m.Bind_Authentik')}}
      </LegacyButton>
      <Tag v-else color="success">{{$t('m.Authentik_Bound')}}</Tag>
    </div>

    <p class="section-title">{{$t('m.Sessions')}}</p>
    <div class="flex-container setting-content">
      <template v-for="session in sessions">
        <Card :padding="20" class="flex-child">
          <template #title><span  style="line-height: 20px">{{session.ip}}</span></template>
          <template #extra><div >
            <span v-if="session.current_session" class="session-current-pill">Current</span>
            <LegacyButton v-else
                    type="warning"
                    size="small"
                    @click="deleteSession(session.session_key)">Revoke
            </LegacyButton>
          </div></template>
          <Form :label-width="100">
            <FormItem label="OS :" class="item">
              {{ platformForSession(session) }}
            </FormItem>
            <FormItem label="Browser :" class="item">
              {{ browserForSession(session) }}
            </FormItem>
            <FormItem label="Last Activity :" class="item">
              {{ $filters.localtime(session.last_activity) }}
            </FormItem>
          </Form>
        </Card>
      </template>
    </div>

    <template v-if="!authentikManaged">
      <p class="section-title">{{$t('m.Two_Factor_Authentication')}}</p>
      <div class="mini-container setting-content">
      <Form>
        <Alert v-if="TFAOpened"
               type="success"
               class="notice"
               showIcon>You have enabled two-factor authentication.
        </Alert>
        <FormItem v-if="!TFAOpened">
          <div class="oj-relative">
            <img :src="qrcodeSrc" id="qr-img">
            <Spin size="large" fix v-if="loadingQRcode"></Spin>
          </div>
        </FormItem>
        <template v-if="!loadingQRcode">
          <FormItem style="width: 250px">
            <Input v-model="formTwoFactor.code" placeholder="Enter the code from your application"/>
          </FormItem>
          <LegacyButton type="primary"
                  :loading="loadingBtn"
                  @click="updateTFA(false)"
                  v-if="!TFAOpened">Open TFA
          </LegacyButton>
          <LegacyButton type="error"
                  :loading="loadingBtn"
                  @click="closeTFA"
                  v-else>Close TFA
          </LegacyButton>
        </template>
      </Form>
      </div>
    </template>
  </div>
</template>
<script>
  import api from '@oj/api'
  import {mapGetters, mapActions} from '@/store/compat'
  import { detectCurrentPlatform, formatBrowser, formatPlatform } from '@/utils/device'

  export default {
    data () {
      return {
        qrcodeSrc: '',
        loadingQRcode: false,
        loadingBtn: false,
        formTwoFactor: {
          code: ''
        },
        sessions: [],
        currentPlatform: ''
      }
    },
    async mounted () {
      this.getSessions()
      if (!this.authentikManaged && !this.TFAOpened) {
        this.getAuthImg()
      }
      this.currentPlatform = await detectCurrentPlatform()
    },
    methods: {
      ...mapActions(['getProfile']),
      bindAuthentik () {
        const url = this.authProviders.authentik && this.authProviders.authentik.link_url
        if (url) window.location.assign(url)
      },
      getAuthImg () {
        this.loadingQRcode = true
        api.twoFactorAuth('get').then(res => {
          this.loadingQRcode = false
          this.qrcodeSrc = res.data.data
        })
      },
      getSessions () {
        api.getSessions().then(res => {
          let data = res.data.data
          // 将当前session放到第一个
          let sessions = data.filter(session => {
            return session.current_session
          })
          data.forEach(session => {
            if (!session.current_session) {
              sessions.push(session)
            }
          })
          this.sessions = sessions
        })
      },
      platformForSession (session) {
        return session.current_session && this.currentPlatform
          ? this.currentPlatform
          : formatPlatform(session.user_agent)
      },
      browserForSession (session) {
        return formatBrowser(session.user_agent)
      },
      deleteSession (sessionKey) {
        this.$Modal.confirm({
          title: 'Confirm',
          content: 'Are you sure to revoke the session?',
          onOk: () => {
            api.deleteSession(sessionKey).then(res => {
              this.getSessions()
            }, _ => {
            })
          }
        })
      },
      closeTFA () {
        this.$Modal.confirm({
          title: 'Confirm',
          content: 'Two-factor Authentication is a powerful tool to protect your account, are you sure to close it?',
          onOk: () => {
            this.updateTFA(true)
          }
        })
      },
      updateTFA (close) {
        let method = close === false ? 'post' : 'put'
        this.loadingBtn = true
        api.twoFactorAuth(method, this.formTwoFactor).then(res => {
          this.loadingBtn = false
          this.getProfile()
          if (close === true) {
            this.getAuthImg()
            this.formTwoFactor.code = ''
          }
          this.formTwoFactor.code = ''
        }, err => {
          this.formTwoFactor.code = ''
          this.loadingBtn = false
          if (err.data.data.indexOf('session') > -1) {
            this.getProfile()
            this.getAuthImg()
          }
        })
      }
    },
    computed: {
      ...mapGetters(['user', 'authProviders']),
      authentikEnabled () {
        return !!(this.authProviders.authentik && this.authProviders.authentik.enabled)
      },
      authentikLinked () {
        return !!(this.authProviders.authentik && this.authProviders.authentik.linked)
      },
      authentikManaged () {
        return this.authentikEnabled && this.authentikLinked
      },
      TFAOpened () {
        return this.user && this.user.two_factor_auth
      }
    }
  }
</script>

<style lang="less" scoped>
  .identity-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    margin-bottom: 28px;
    padding: 18px 20px;
    border: 1px solid var(--oj-border);
    border-radius: var(--oj-radius-medium);
    background: var(--oj-surface-muted);
  }

  .identity-eyebrow {
    color: var(--oj-accent);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .16em;
  }

  .identity-title {
    margin-top: 6px;
    color: var(--oj-text-muted);
    font-size: 13px;
    line-height: 1.5;
  }

  .notice {
    font-size: 16px;
    margin-bottom: 20px;
    display: inline-block;
  }

  .session-current-pill {
    display: inline-flex;
    height: 24px;
    align-items: center;
    padding: 0 10px;
    border: 1px solid #b9dfc6;
    border-radius: 9999px;
    background: #edf8f0;
    color: #277a45;
    font-size: 12px;
    font-weight: 650;
    line-height: 1;
    white-space: nowrap;
  }

  .oj-relative {
    width: 150px;
    #qr-img {
      width: 300px;
      margin: -10px 0 -30px -20px;
    }
  }

  .flex-container {
    flex-flow: row wrap;
    justify-content: flex-start;
    .flex-child {
      flex: 1 0;
      max-width: 350px;
      margin-right: 30px;
      margin-bottom: 30px;
      .item {
        margin-bottom: 0;
      }
    }
  }
</style>
