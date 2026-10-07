<template>
  <div class="auth-panel">
    <div v-if="authentikEnabled" class="sso-card">
      <div class="sso-eyebrow">AUTHENTIK</div>
      <p class="sso-copy">{{$t('m.Register_through_Authentik')}}</p>
      <LegacyButton type="primary" long class="sso-button" @click="goAuthentikRegister">
        {{$t('m.Register_with_Authentik')}}
      </LegacyButton>
      <a class="sso-register" @click.stop="switchMode('login')">
        {{$t('m.Already_Registed')}}
      </a>
    </div>

    <template v-else>
      <Form ref="formRegister" :model="formRegister" :rules="ruleRegister">
        <FormItem prop="username">
          <Input type="text" v-model="formRegister.username" :placeholder="$t('m.RegisterUsername')" size="large" @on-enter="handleRegister">
          <template #prepend><Icon type="ios-person-outline" ></Icon></template>
          </Input>
        </FormItem>
        <FormItem prop="email">
          <Input v-model="formRegister.email" :placeholder="$t('m.Email_Address')" size="large" @on-enter="handleRegister">
          <template #prepend><Icon type="ios-email-outline" ></Icon></template>
          </Input>
        </FormItem>
        <FormItem prop="password">
          <Input type="password" v-model="formRegister.password" :placeholder="$t('m.RegisterPassword')" size="large" @on-enter="handleRegister">
          <template #prepend><Icon type="ios-locked-outline" ></Icon></template>
          </Input>
        </FormItem>
        <FormItem prop="passwordAgain">
          <Input type="password" v-model="formRegister.passwordAgain" :placeholder="$t('m.Password_Again')" size="large" @on-enter="handleRegister">
          <template #prepend><Icon type="ios-locked-outline" ></Icon></template>
          </Input>
        </FormItem>
        <FormItem prop="captcha" style="margin-bottom:10px">
          <div class="oj-captcha">
            <div class="oj-captcha-code">
              <Input v-model="formRegister.captcha" :placeholder="$t('m.Captcha')" size="large" @on-enter="handleRegister">
              <template #prepend><Icon type="ios-lightbulb-outline" ></Icon></template>
              </Input>
            </div>
            <div class="oj-captcha-img">
              <Tooltip content="Click to refresh" placement="top">
                <img :src="captchaSrc" @click="getCaptchaSrc"/>
              </Tooltip>
            </div>
          </div>
        </FormItem>
      </Form>
      <div class="footer">
        <LegacyButton
          type="primary"
          @click="handleRegister"
          class="btn" long
          :loading="btnRegisterLoading">
          {{$t('m.UserRegister')}}
        </LegacyButton>
        <LegacyButton
          type="ghost"
          @click="switchMode('login')"
          class="btn" long>
          {{$t('m.Already_Registed')}}
        </LegacyButton>
      </div>
    </template>
  </div>
</template>
<script>
  import { mapGetters, mapActions } from '@/store/compat'
  import api from '@oj/api'
  import { FormMixin } from '@oj/components/mixins'

  export default {
    mixins: [FormMixin],
    mounted () {
      if (!this.authentikEnabled) this.getCaptchaSrc()
    },
    data () {
      const CheckUsernameNotExist = (rule, value, callback) => {
        api.checkUsernameOrEmail(value, undefined).then(res => {
          if (res.data.data.username === true) {
            return callback(new Error(this.$t('m.The_username_already_exists')))
          } else {
            callback()
          }
        }, _ => callback())
      }
      const CheckEmailNotExist = (rule, value, callback) => {
        api.checkUsernameOrEmail(undefined, value).then(res => {
          if (res.data.data.email === true) {
            return callback(new Error(this.$t('m.The_email_already_exists')))
          } else {
            callback()
          }
        }, _ => callback())
      }
      const CheckPassword = (rule, value, callback) => {
        if (this.formRegister.password !== '') {
          // 对第二个密码框再次验证
          this.$refs.formRegister.validateField('passwordAgain')
        }
        callback()
      }

      const CheckAgainPassword = (rule, value, callback) => {
        if (value !== this.formRegister.password) {
          return callback(new Error(this.$t('m.password_does_not_match')))
        }
        callback()
      }

      return {
        btnRegisterLoading: false,
        formRegister: {
          username: '',
          password: '',
          passwordAgain: '',
          email: '',
          captcha: ''
        },
        ruleRegister: {
          username: [
            {required: true, trigger: 'blur'},
            {validator: CheckUsernameNotExist, trigger: 'blur'}
          ],
          email: [
            {required: true, type: 'email', trigger: 'blur'},
            {validator: CheckEmailNotExist, trigger: 'blur'}
          ],
          password: [
            {required: true, trigger: 'blur', min: 6, max: 20},
            {validator: CheckPassword, trigger: 'blur'}
          ],
          passwordAgain: [
            {required: true, validator: CheckAgainPassword, trigger: 'change'}
          ],
          captcha: [
            {required: true, trigger: 'blur', min: 1, max: 10}
          ]
        }
      }
    },
    methods: {
      ...mapActions(['changeModalStatus', 'getProfile']),
      switchMode (mode) {
        this.changeModalStatus({
          mode,
          visible: true
        })
      },
      goAuthentikRegister () {
        const url = this.authProviders.authentik && this.authProviders.authentik.register_url
        if (url) window.location.assign(url)
      },
      handleRegister () {
        this.validateForm('formRegister').then(valid => {
          let formData = Object.assign({}, this.formRegister)
          delete formData['passwordAgain']
          this.btnRegisterLoading = true
          api.register(formData).then(res => {
            this.$success(this.$t('m.Thanks_for_registering'))
            this.switchMode('login')
            this.btnRegisterLoading = false
          }, _ => {
            this.getCaptchaSrc()
            this.formRegister.captcha = ''
            this.btnRegisterLoading = false
          })
        })
      }
    },
    computed: {
      ...mapGetters(['website', 'modalStatus', 'authProviders']),
      authentikEnabled () {
        return !!(this.authProviders.authentik && this.authProviders.authentik.enabled)
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
