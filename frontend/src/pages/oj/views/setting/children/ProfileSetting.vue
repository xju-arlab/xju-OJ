<template>
  <div class="setting-main">
    <Alert v-if="onboardingRequired" type="warning" show-icon>
      {{ $t('m.Profile_Onboarding_Notice') }}
    </Alert>

    <div class="section-title">{{$t('m.Avatar_Setting')}}</div>
    <div class="avatar-setting-card">
      <div class="avatar-preview" :class="{'is-loading': loadingUploadBtn}">
        <img v-if="avatarSrc && !avatarFailed"
             :key="avatarSrc"
             :src="avatarSrc"
             :alt="$t('m.Avatar_Setting')"
             @load="avatarFailed = false"
             @error="avatarFailed = true">
        <span v-else class="avatar-fallback">{{ avatarInitial }}</span>
        <span v-if="loadingUploadBtn" class="avatar-loading" aria-hidden="true">
          <Icon type="loading" size="22"></Icon>
        </span>
      </div>
      <div class="avatar-setting-content">
        <LegacyButton type="primary"
                      class="avatar-upload-button"
                      :loading="loadingUploadBtn"
                      :disabled="loadingUploadBtn"
                      @click="openAvatarPicker">
          <Icon v-if="!loadingUploadBtn" type="upload" size="17"></Icon>
          {{ $t('m.Reupload_Avatar') }}
        </LegacyButton>
        <input ref="avatarInput"
               class="avatar-file-input"
               type="file"
               accept="image/jpeg,image/png,image/bmp,image/gif,image/webp"
               @change="handleAvatarChange">
      </div>
    </div>

    <div class="section-title">{{$t('m.Profile_Setting')}}</div>
    <Form ref="formProfile" :model="formProfile">
      <Row type="flex" :gutter="30" justify="space-around">
        <Col :span="11">
          <FormItem :label="$t('m.Real_Name')" required>
            <Input v-model="formProfile.real_name"/>
          </FormItem>
          <Form-item :label="$t('m.Student_ID')" required>
            <Input v-model="formProfile.student_id"/>
          </Form-item>
          <Form-item :label="$t('m.School')">
            <Input v-model="formProfile.school"/>
          </Form-item>
          <Form-item :label="$t('m.Major')">
            <Input v-model="formProfile.major"/>
          </Form-item>
          <FormItem :label="$t('m.Interface_Language')">
            <Select v-model="formProfile.language">
              <Option v-for="lang in languages" :key="lang.value" :value="lang.value">{{lang.label}}</Option>
            </Select>
          </FormItem>
          <Form-item>
            <LegacyButton type="primary" @click="updateProfile" :loading="loadingSaveBtn">{{ $t('m.Save_All') }}</LegacyButton>
          </Form-item>
        </Col>

        <Col :span="11">
          <Form-item :label="$t('m.Mood')">
            <Input v-model="formProfile.mood"/>
          </Form-item>
          <Form-item :label="$t('m.Blog')">
            <Input v-model="formProfile.blog"/>
          </Form-item>
          <Form-item :label="$t('m.Github')">
            <Input v-model="formProfile.github"/>
          </Form-item>
        </Col>
      </Row>
    </Form>
  </div>
</template>

<script>
  import api from '@oj/api'
  import utils from '@/utils/utils'
  import {types} from '@/store'
  import {languages} from '@/i18n'

  const MAX_SOURCE_SIZE = 12 * 1024 * 1024
  const AVATAR_SIZE = 512

  export default {
    data () {
      return {
        loadingSaveBtn: false,
        loadingUploadBtn: false,
        avatarFailed: false,
        avatarPreviewUrl: '',
        avatarVersion: 0,
        languages: languages,
        formProfile: {
          real_name: '',
          student_id: '',
          mood: '',
          major: '',
          blog: '',
          school: '',
          github: '',
          language: ''
        }
      }
    },
    mounted () {
      const profile = this.$store.state.user.profile
      Object.keys(this.formProfile).forEach(element => {
        if (profile[element] !== undefined) {
          this.formProfile[element] = profile[element]
        }
      })
    },
    beforeUnmount () {
      this.clearAvatarPreview()
    },
    methods: {
      openAvatarPicker () {
        if (!this.loadingUploadBtn) this.$refs.avatarInput?.click()
      },
      checkFileType (file) {
        const supportedMimeTypes = new Set(['image/jpeg', 'image/png', 'image/bmp', 'image/gif', 'image/webp'])
        if (!supportedMimeTypes.has(file.type) && !/\.(gif|jpg|jpeg|png|bmp|webp)$/i.test(file.name)) {
          this.$Notice.warning({
            title: this.$t('m.Unsupported_File_Type'),
            desc: this.$t('m.Select_Image_File')
          })
          return false
        }
        return true
      },
      checkFileSize (file) {
        if (file.size > MAX_SOURCE_SIZE) {
          this.$Notice.warning({
            title: this.$t('m.Image_Too_Large'),
            desc: this.$t('m.Avatar_Source_Size_Limit')
          })
          return false
        }
        return true
      },
      async handleAvatarChange (event) {
        const file = event.target.files?.[0]
        event.target.value = ''
        if (!file || !this.checkFileType(file) || !this.checkFileSize(file)) return

        this.loadingUploadBtn = true
        this.avatarFailed = false
        let uploadStarted = false
        try {
          const avatarBlob = await this.createAvatarBlob(file)
          this.setAvatarPreview(avatarBlob)
          const form = new window.FormData()
          form.append('image', new window.File([avatarBlob], 'avatar.webp', {type: 'image/webp'}))
          uploadStarted = true
          await api.uploadAvatar(form)
          await this.$store.dispatch('getProfile')
          this.avatarVersion = Date.now()
          await this.showStoredAvatar()
          this.$success(this.$t('m.Avatar_Updated'))
        } catch (error) {
          this.clearAvatarPreview()
          this.$error(this.$t(uploadStarted ? 'm.Avatar_Upload_Failed' : 'm.Avatar_Compression_Failed'))
        } finally {
          this.loadingUploadBtn = false
        }
      },
      loadImage (file) {
        return new Promise((resolve, reject) => {
          const sourceUrl = URL.createObjectURL(file)
          const image = new window.Image()
          image.onload = () => {
            URL.revokeObjectURL(sourceUrl)
            resolve(image)
          }
          image.onerror = () => {
            URL.revokeObjectURL(sourceUrl)
            reject(new Error('Image decoding failed'))
          }
          image.src = sourceUrl
        })
      },
      canvasToWebP (canvas) {
        return new Promise((resolve, reject) => {
          canvas.toBlob(blob => {
            if (!blob || blob.type !== 'image/webp') {
              reject(new Error('WebP encoding failed'))
              return
            }
            resolve(blob)
          }, 'image/webp', 0.84)
        })
      },
      async createAvatarBlob (file) {
        const image = await this.loadImage(file)
        const sourceSize = Math.min(image.naturalWidth, image.naturalHeight)
        if (!sourceSize) throw new Error('Image has no pixels')

        const sourceX = Math.round((image.naturalWidth - sourceSize) / 2)
        const sourceY = Math.round((image.naturalHeight - sourceSize) / 2)
        const canvas = document.createElement('canvas')
        canvas.width = AVATAR_SIZE
        canvas.height = AVATAR_SIZE
        const context = canvas.getContext('2d')
        if (!context) throw new Error('Canvas is unavailable')
        context.imageSmoothingEnabled = true
        context.imageSmoothingQuality = 'high'
        context.drawImage(
          image,
          sourceX,
          sourceY,
          sourceSize,
          sourceSize,
          0,
          0,
          AVATAR_SIZE,
          AVATAR_SIZE
        )
        return this.canvasToWebP(canvas)
      },
      setAvatarPreview (blob) {
        this.clearAvatarPreview()
        this.avatarPreviewUrl = URL.createObjectURL(blob)
      },
      clearAvatarPreview () {
        if (this.avatarPreviewUrl) URL.revokeObjectURL(this.avatarPreviewUrl)
        this.avatarPreviewUrl = ''
      },
      async showStoredAvatar () {
        const previewUrl = this.avatarPreviewUrl
        this.avatarPreviewUrl = ''
        this.avatarFailed = false
        // Switch the rendered image away from the blob URL before revoking it.
        // Otherwise the revoke can emit an error and lock the UI on initials.
        await this.$nextTick()
        if (previewUrl) URL.revokeObjectURL(previewUrl)
      },
      updateProfile () {
        const missing = []
        if (!String(this.formProfile.real_name || '').trim()) missing.push(this.$t('m.Real_Name'))
        if (!String(this.formProfile.student_id || '').trim()) missing.push(this.$t('m.Student_ID'))
        if (missing.length) {
          const separator = ['zh-CN', 'zh-TW'].includes(this.$i18n.locale) ? '、' : ', '
          this.$Notice.warning({
            title: this.$t('m.Profile_Required_Title'),
            desc: this.$t('m.Profile_Required_Fields', {fields: missing.join(separator)})
          })
          return
        }
        this.loadingSaveBtn = true
        const updateData = {...this.formProfile}
        api.updateProfile(updateData).then(res => {
          this.$success('Success')
          this.$store.commit(types.CHANGE_PROFILE, {profile: res.data.data})
          if (this.$route.query.onboarding === '1') {
            this.$router.replace({query: {}})
          }
          this.loadingSaveBtn = false
        }, _ => {
          this.loadingSaveBtn = false
        })
      }
    },
    computed: {
      onboardingRequired () {
        return this.$route.query.onboarding === '1' || this.$store.state.user.profile.oj_onboarding_completed === false
      },
      avatarSrc () {
        if (this.avatarPreviewUrl) return this.avatarPreviewUrl
        const avatar = this.$store.state.user.profile.avatar
        if (!avatar) return ''
        if (!this.avatarVersion) return avatar
        return `${avatar}${avatar.includes('?') ? '&' : '?'}v=${this.avatarVersion}`
      },
      avatarInitial () {
        const username = this.$store.state.user.profile.user?.username || '?'
        return username.slice(0, 1).toUpperCase()
      }
    },
    watch: {
      avatarSrc () {
        this.avatarFailed = false
      }
    }
  }
</script>

<style lang="less" scoped>
  :deep(.el-form-item.is-required .el-form-item__label::before) {
    color: #c94f4f;
  }

  .avatar-setting-card {
    display: flex;
    align-items: center;
    gap: 24px;
    width: min(100%, 560px);
    margin-bottom: 28px;
    padding: 18px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-bg);
  }

  .avatar-preview {
    position: relative;
    flex: 0 0 112px;
    width: 112px;
    height: 112px;
    overflow: hidden;
    border: 1px solid var(--color-border);
    border-radius: 50%;
    background: var(--color-bg-subtle);

    img,
    .avatar-fallback {
      display: grid;
      width: 100%;
      height: 100%;
      place-items: center;
    }

    img {
      object-fit: cover;
    }

    .avatar-fallback {
      color: var(--color-text-muted);
      font-size: 34px;
      font-weight: 600;
    }
  }

  .avatar-loading {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    background: rgb(255 255 255 / 72%);

    :deep(svg) {
      animation: avatar-spin 900ms linear infinite;
    }
  }

  .avatar-setting-content {
    min-width: 0;
  }

  .avatar-upload-button :deep(.legacy-icon) {
    display: inline-flex;
    align-items: center;
  }

  .avatar-file-input {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    clip-path: inset(50%);
    white-space: nowrap;
  }

  @keyframes avatar-spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 760px) {
    .avatar-setting-card {
      align-items: flex-start;
      gap: 16px;
      padding: 16px;
    }

    .avatar-preview {
      flex-basis: 88px;
      width: 88px;
      height: 88px;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .avatar-loading :deep(svg) { animation-duration: 1.8s; }
  }
</style>
