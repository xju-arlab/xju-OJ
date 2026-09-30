<template>
</template>

<script>
  import { mapGetters } from '@/store/compat'
  import api from '../../api.js'

  export default {
    mounted () {
      const authentik = this.authProviders.authentik
      if (authentik && authentik.enabled && authentik.linked) {
        this.$store.dispatch('clearProfile')
        window.location.assign('/api/auth/oidc/logout/?next=/')
        return
      }
      api.logout().then(res => {
        this.$store.dispatch('clearProfile')
        this.$router.replace({
          path: '/'
        })
      })
    },
    computed: {
      ...mapGetters(['authProviders'])
    }
  }
</script>
