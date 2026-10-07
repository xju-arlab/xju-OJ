<template>
  <div class="auth-panel">
    <div v-if="authentikEnabled" class="sso-card">
      <div class="sso-eyebrow">AUTHENTIK</div>
      <p class="sso-copy">{{$t('m.Authentik_Account_Notice')}}</p>
      <LegacyButton type="primary" long class="sso-button" :loading="btnLoginLoading" @click="startAuthentikLogin">
        {{$t('m.Login_with_Authentik')}}
      </LegacyButton>
      <a class="sso-register" @click.stop="goAuthentikRegister">
        {{$t('m.Register_with_Authentik')}}
      </a>
      <p class="legacy-entry">
        <a href="https://auth.icthub.top/if/flow/icthub-bind-email/">旧 Authentik 账号未绑定邮箱？先验证邮箱</a>
      </p>
      <p class="legacy-entry">
        <a @click.stop="toggleLegacyLink">旧 OJ 账号未绑定邮箱？关联统一账号</a>
      </p>
    </div>

    <div v-if="authentikEnabled && showLegacyLink" class="legacy-link-card">
      <p>输入旧 OJ 账号凭据。之后请登录已经验证邮箱的 Authentik 账号，完成关联。</p>
      <Form ref="legacyLinkForm" :model="legacyLinkForm" :rules="legacyLinkRules">
        <FormItem prop="username"><Input v-model="legacyLinkForm.username" placeholder="旧 OJ 用户名" size="large"/></FormItem>
        <FormItem prop="password"><Input v-model="legacyLinkForm.password" type="password" placeholder="旧 OJ 密码" size="large"/></FormItem>
        <FormItem><Input v-model="legacyLinkForm.tfa_code" placeholder="原有两步验证码（如已启用）" size="large"/></FormItem>
        <FormItem prop="captcha" class="legacy-captcha">
          <Input v-model="legacyLinkForm.captcha" placeholder="图形验证码" size="large"/>
          <img :src="captchaSrc" alt="图形验证码，点击刷新" @click="getCaptchaSrc"/>
        </FormItem>
        <LegacyButton type="primary" long :loading="legacyLinkLoading" @click="startLegacyLink">验证旧账号并继续</LegacyButton>
      </Form>
    </div>

    <div v-if="authentikEnabled && localLoginEnabled" class="auth-divider">
      <span>or</span>
    </div>

    <Form v-if="localLoginEnabled" ref="formLogin" :model="formLogin" :rules="ruleLogin">
      <FormItem prop="username">
        <Input type="text" v-model="formLogin.username" :placeholder="$t('m.LoginUsername')" size="large" @on-enter="handleLogin">
        <template #prepend><Icon type="ios-person-outline" ></Icon></template>
        </Input>
      </FormItem>
      <FormItem prop="password">
        <Input type="password" v-model="formLogin.password" :placeholder="$t('m.LoginPassword')" size="large" @on-enter="handleLogin">
        <template #prepend><Icon type="ios-locked-outline" ></Icon></template>
        </Input>
      </FormItem>
      <FormItem prop="tfa_code" v-if="tfaRequired">
        <Input v-model="formLogin.tfa_code" :placeholder="$t('m.TFA_Code')">
        <template #prepend><Icon type="ios-lightbulb-outline" ></Icon></template>
        </Input>
      </FormItem>
    </Form>
    <div v-if="localLoginEnabled" class="footer">
      <LegacyButton
        type="primary"
        @click="handleLogin"
        class="btn" long
        :loading="btnLoginLoading">
        {{$t('m.UserLogin')}}
      </LegacyButton>
      <a v-if="website.allow_register && localRegisterEnabled" @click.stop="handleBtnClick('register')">{{$t('m.No_Account')}}</a>
      <a @click.stop="goResetPassword" style="float: right">{{$t('m.Forget_Password')}}</a>
    </div>
  </div>
</template>
<script>
  import { mapGetters, mapActions } from '@/store/compat'
  import api from '@oj/api'
  import { FormMixin } from '@oj/components/mixins'
  import runtime from '@/utils/runtime'

  export default {
    mixins: [FormMixin],
    data () {
      const CheckRequiredTFA = (rule, value, callback) => {
        if (value !== '') {
          api.tfaRequiredCheck(value).then(res => {
            this.tfaRequired = res.data.data.result
          })
        }
        callback()
      }

      return {
        tfaRequired: false,
        btnLoginLoading: false,
        showLegacyLink: false,
        legacyLinkLoading: false,
        legacyLinkForm: { username: '', password: '', tfa_code: '', captcha: '' },
        legacyLinkRules: {
          username: [{required: true, trigger: 'blur'}],
          password: [{required: true, trigger: 'blur'}],
          captcha: [{required: true, trigger: 'blur'}]
        },
        formLogin: {
          username: runtime.OJ_FRONTEND_DEV_MODE ? runtime.DEV_LOGIN_USERNAME : '',
          password: runtime.OJ_FRONTEND_DEV_MODE ? runtime.DEV_LOGIN_PASSWORD : '',
          tfa_code: ''
        },
        ruleLogin: {
          username: [
            {required: true, trigger: 'blur'},
            {validator: CheckRequiredTFA, trigger: 'blur'}
          ],
          password: [
            {required: true, trigger: 'change', min: 6, max: 20}
          ]
        }
      }
    },
    methods: {
      ...mapActions(['changeModalStatus', 'getProfile']),
      handleBtnClick (mode) {
        this.changeModalStatus({
          mode,
          visible: true
        })
      },
      handleLogin () {
        this.validateForm('formLogin').then(valid => {
          this.btnLoginLoading = true
          let formData = Object.assign({}, this.formLogin)
          if (!this.tfaRequired) {
            delete formData['tfa_code']
          }
          api.login(formData).then(res => {
            this.btnLoginLoading = false
            this.changeModalStatus({visible: false})
            this.getProfile()
            this.$success(this.$t('m.Welcome_back'))
          }, _ => {
            this.btnLoginLoading = false
          })
        })
      },
      goResetPassword () {
        this.changeModalStatus({visible: false})
        this.$router.push({name: 'apply-reset-password'})
      },
      startAuthentikLogin () {
        if (runtime.OJ_FRONTEND_DEV_MODE) {
          this.btnLoginLoading = true
          api.login({
            username: runtime.DEV_LOGIN_USERNAME,
            password: runtime.DEV_LOGIN_PASSWORD
          }).then(() => {
            this.changeModalStatus({visible: false})
            this.getProfile()
            this.$success(this.$t('m.Welcome_back'))
          }, () => {}).finally(() => {
            this.btnLoginLoading = false
          })
          return
        }
        const url = new URL('/api/auth/oidc/login/', window.location.origin)
        url.searchParams.set('next', '/')
        window.location.assign(url.toString())
      },
      goAuthentikRegister () {
        const url = this.authProviders.authentik && this.authProviders.authentik.register_url
        if (url) window.location.assign(url)
      },
      toggleLegacyLink () {
        this.showLegacyLink = !this.showLegacyLink
        if (this.showLegacyLink) this.getCaptchaSrc()
      },
      startLegacyLink () {
        this.validateForm('legacyLinkForm').then(valid => {
          if (!valid) return
          this.legacyLinkLoading = true
          api.legacyEmailLink(this.legacyLinkForm).then(res => {
            window.location.assign(res.data.data.authorization_url)
          }, () => {
            this.legacyLinkForm.captcha = ''
            this.getCaptchaSrc()
            this.legacyLinkLoading = false
          })
        })
      }
    },
    computed: {
      ...mapGetters(['website', 'modalStatus', 'authProviders']),
      authentikEnabled () {
        return !!(this.authProviders.authentik && this.authProviders.authentik.enabled)
      },
      localLoginEnabled () {
        return !this.authProviders.local || this.authProviders.local.login_enabled !== false
      },
      localRegisterEnabled () {
        return !this.authProviders.local || this.authProviders.local.register_enabled !== false
      },
      visible: {
        get () {
          return this.modalStatus.visible
        },
        set (value) {
          this.changeModalStatus({visible: value})
        }
      }
    }
  }
</script>

<style scoped lang="less">
  .auth-panel {
    max-width: 420px;
    margin: 0 auto;
    padding: 2px 2px 0;
  }

  .sso-card {
    padding: 16px;
    border: 1px solid var(--oj-border);
    border-radius: var(--oj-radius-medium);
    background: var(--oj-surface-muted);
    text-align: center;
  }

  .sso-eyebrow {
    color: var(--oj-accent);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .16em;
  }

  .sso-copy {
    margin: 8px 0 14px;
    color: var(--oj-text-muted);
    font-size: 13px;
    line-height: 1.6;
  }

  .sso-button {
    margin-bottom: 10px;
  }

  .sso-register {
    color: var(--oj-accent);
    cursor: pointer;
    font-size: 13px;
  }

  .legacy-entry {
    margin: 8px 0 0;
    font-size: 12px;
  }

  .legacy-entry a {
    color: var(--oj-accent);
    cursor: pointer;
  }

  .legacy-link-card {
    margin-top: 12px;
    padding: 16px;
    border: 1px solid var(--oj-border);
    border-radius: var(--oj-radius-medium);
    background: var(--oj-surface-muted);
  }

  .legacy-link-card p {
    margin: 0 0 12px;
    color: var(--oj-text-muted);
    font-size: 13px;
    line-height: 1.6;
  }

  .legacy-captcha img {
    width: 90px;
    height: 30px;
    margin-top: 6px;
    cursor: pointer;
  }

  .auth-divider {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 18px 0;
    color: var(--oj-text-faint);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: .12em;
  }

  .auth-divider::before,
  .auth-divider::after {
    content: '';
    height: 1px;
    flex: 1;
    background: var(--oj-border);
  }

  .footer {
    overflow: auto;
    margin-top: 20px;
    margin-bottom: -15px;
    text-align: left;
    .btn {
      margin: 0 0 15px 0;
      &:last-child {
        margin: 0;
      }
    }
  }
</style>
