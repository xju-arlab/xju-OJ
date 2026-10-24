<template>
  <section class="prep-panel" aria-labelledby="prep-roles-title">
    <header class="prep-panel-heading">
      <div>
        <h2 id="prep-roles-title">{{ $t('m.Prep_Roles') }}</h2>
        <p>{{ $t('m.Prep_Roles_Intro') }}</p>
      </div>
    </header>

    <form v-if="canManagePrep" class="prep-member-form" @submit.prevent="addMember">
      <el-autocomplete v-model="newMember.username"
                       class="prep-member-user"
                       :fetch-suggestions="searchUsers"
                       :trigger-on-focus="false"
                       value-key="username"
                       :placeholder="$t('m.Prep_Username_Placeholder')"
                       @select="item => newMember.username = item.username"></el-autocomplete>
      <el-select v-model="newMember.role" class="prep-member-role">
        <el-option v-for="role in assignableRoles" :key="role" :value="role" :label="roleLabel(role)"></el-option>
      </el-select>
      <el-button type="primary" native-type="submit" :loading="adding">{{ $t('m.Prep_Add_Member') }}</el-button>
    </form>

    <table class="prep-member-table">
      <thead>
        <tr>
          <th>{{ $t('m.Username') }}</th>
          <th>{{ $t('m.Prep_Role') }}</th>
          <th class="role-permissions">{{ $t('m.Prep_Role_Permissions') }}</th>
          <th v-if="canManagePrep" class="actions-column"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="creator">
          <td><router-link :to="userHome(creator.username)">{{ creator.username }}</router-link></td>
          <td><span class="role-pill role-creator">{{ roleLabel('Creator') }}</span></td>
          <td class="role-permissions">{{ $t('m.Prep_Role_Creator_Permissions') }}</td>
          <td v-if="canManagePrep"></td>
        </tr>
        <tr v-for="member in members" :key="member.id">
          <td><router-link :to="userHome(member.user.username)">{{ member.user.username }}</router-link></td>
          <td>
            <el-select v-if="canManagePrep" :model-value="member.role" size="small" class="prep-member-role"
                       @change="role => changeRole(member, role)">
              <el-option v-for="role in assignableRoles" :key="role" :value="role" :label="roleLabel(role)"></el-option>
            </el-select>
            <span v-else :class="['role-pill', `role-${member.role.toLowerCase()}`]">{{ roleLabel(member.role) }}</span>
          </td>
          <td class="role-permissions">{{ $t(`m.Prep_Role_${member.role}_Permissions`) }}</td>
          <td v-if="canManagePrep" class="actions-column">
            <el-button text type="danger" size="small" @click="removeMember(member)">{{ $t('m.Prep_Remove') }}</el-button>
          </td>
        </tr>
        <tr v-if="!loading && !members.length">
          <td :colspan="canManagePrep ? 4 : 3" class="prep-empty">{{ $t('m.Prep_No_Members') }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script>
import api from '@oj/api'
import { mapGetters } from '@/store/compat'

export default {
  name: 'ContestPrepRoles',
  data () {
    return {
      loading: false,
      adding: false,
      creator: null,
      members: [],
      assignableRoles: ['Setter', 'Verifier'],
      newMember: { username: '', role: 'Setter' }
    }
  },
  computed: {
    ...mapGetters(['canManagePrep']),
    contestID () {
      return this.$route.params.contestID
    }
  },
  mounted () {
    this.load()
  },
  methods: {
    roleLabel (role) {
      return this.$t(`m.Prep_Role_${role}`)
    },
    userHome (username) {
      return { name: 'user-home', query: { username } }
    },
    async load () {
      this.loading = true
      try {
        const res = await api.getPrepMembers(this.contestID)
        this.creator = res.data.data.creator
        this.members = res.data.data.members
      } catch (_) {
        this.members = []
      } finally {
        this.loading = false
      }
    },
    searchUsers (keyword, callback) {
      if (!keyword) return callback([])
      api.searchPrepUsers(this.contestID, keyword)
        .then(res => callback(res.data.data))
        .catch(() => callback([]))
    },
    async addMember () {
      const username = this.newMember.username.trim()
      if (!username) return
      this.adding = true
      try {
        await api.addPrepMember(this.contestID, username, this.newMember.role)
        this.newMember.username = ''
        await this.load()
      } catch (_) {
        // The API client already shows the error.
      } finally {
        this.adding = false
      }
    },
    async changeRole (member, role) {
      try {
        await api.updatePrepMember(this.contestID, member.user.id, role)
        member.role = role
      } catch (_) {
        await this.load()
      }
    },
    removeMember (member) {
      this.$confirm(this.$t('m.Prep_Remove_Confirm', { username: member.user.username }), this.$t('m.Prep_Remove'), {
        type: 'warning'
      }).then(async () => {
        await api.removePrepMember(this.contestID, member.user.id)
        await this.load()
      }).catch(() => {})
    }
  }
}
</script>

<style scoped lang="less">
@import "@/styles/contest-prep.less";

.prep-member-form { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 16px; }
.prep-member-user { flex: 0 1 320px; min-width: 200px; }
.prep-member-role { width: 140px; }
.prep-member-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  th, td { padding: 10px 12px; border-bottom: 1px solid var(--color-border); text-align: left; vertical-align: middle; }
  th { color: var(--color-text-muted); font-weight: 600; }
  .actions-column { width: 90px; text-align: right; }
}
.role-permissions { color: var(--color-text-muted); }
.role-pill { display: inline-flex; height: 22px; align-items: center; padding: 0 8px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 600; }
.role-creator { background: var(--tag-tools-bg); color: var(--color-link); }
.role-setter { background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
.role-verifier { background: var(--color-bg-subtle); color: var(--color-text-muted); }
@media (max-width: 640px) {
  .role-permissions { display: none; }
}
</style>
