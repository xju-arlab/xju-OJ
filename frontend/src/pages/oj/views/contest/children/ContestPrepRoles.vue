<template>
  <section class="prep-panel" :aria-label="$t('m.Prep_Roles')">

    <form v-if="canManagePrep" class="prep-member-form" @submit.prevent="addMember">
      <div class="prep-member-user">
        <el-autocomplete v-model="newMember.username"
                         :fetch-suggestions="searchUsers"
                         :trigger-on-focus="false"
                         value-key="username"
                         :placeholder="$t('m.Prep_Username_Placeholder')"
                         @select="item => newMember.username = item.username">
          <template #default="{ item }">
            <span class="suggestion-name">{{ item.username }}</span>
            <span v-if="item.real_name" class="suggestion-real-name">{{ item.real_name }}</span>
          </template>
        </el-autocomplete>
      </div>
      <el-select v-model="newMember.role" class="prep-member-role">
        <el-option v-for="role in assignableRoles" :key="role" :value="role" :label="roleLabel(role)"></el-option>
      </el-select>
      <el-button type="primary" native-type="submit" :loading="adding">{{ $t('m.Prep_Add_Member') }}</el-button>
      <button type="button"
              :class="['invite-button', { 'is-copied': copiedRole, 'is-busy': inviting }]"
              :disabled="inviting"
              @click="copyInvite">
        <span class="invite-label invite-idle" :aria-hidden="copiedRole ? 'true' : 'false'">
          <Icon type="link" />{{ $t('m.Prep_Invite_Link') }}
        </span>
        <span class="invite-label invite-done" :aria-hidden="copiedRole ? 'false' : 'true'" role="status">
          <Icon type="check" />{{ copiedRole ? $t(`m.Prep_Invite_Copied_${copiedRole}`) : '' }}
        </span>
      </button>
      <button v-if="openInviteCount" type="button" class="invite-revoke" @click="revokeInvites">
        {{ $t('m.Prep_Invite_Revoke', { count: openInviteCount }) }}
      </button>
    </form>

    <table class="prep-member-table">
      <thead>
        <tr>
          <th>{{ $t('m.Username') }}</th>
          <th>{{ $t('m.Prep_Role') }}</th>
          <th v-if="canManagePrep" class="actions-column"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="creator">
          <td><router-link :to="userHome(creator.username)">{{ creator.username }}</router-link></td>
          <td><span class="role-pill role-creator">{{ roleLabel('Creator') }}</span></td>
          <td v-if="canManagePrep"></td>
        </tr>
        <tr v-for="member in members" :key="member.id">
          <td><router-link :to="userHome(member.user.username)">{{ member.user.username }}</router-link></td>
          <td>
            <button v-if="canManagePrep" type="button"
                    :class="['role-pill', 'is-toggle', `role-${member.role.toLowerCase()}`, { 'is-busy': switching === member.id }]"
                    :title="$t('m.Prep_Switch_To', { role: roleLabel(otherRole(member.role)) })"
                    :disabled="switching === member.id"
                    @click="toggleRole(member)">
              <span>{{ roleLabel(member.role) }}</span>
              <Icon type="swap" class="role-swap" />
            </button>
            <span v-else :class="['role-pill', `role-${member.role.toLowerCase()}`]">{{ roleLabel(member.role) }}</span>
          </td>
          <td v-if="canManagePrep" class="actions-column">
            <el-button text type="danger" size="small" @click="removeMember(member)">{{ $t('m.Prep_Remove') }}</el-button>
          </td>
        </tr>
        <tr v-if="!loading && !members.length">
          <td :colspan="canManagePrep ? 3 : 2" class="prep-empty">{{ $t('m.Prep_No_Members') }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script>
import api from '@oj/api'
import { mapGetters } from '@/store/compat'
import { inviteLink } from '../prepInvite'

const COPIED_MS = 2200

async function copyText (text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (_) {
    // Fall back for browsers without the async clipboard (e.g. plain HTTP).
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    let copied = false
    try {
      copied = document.execCommand('copy')
    } catch (_) {
      copied = false
    }
    document.body.removeChild(area)
    return copied
  }
}

export default {
  name: 'ContestPrepRoles',
  data () {
    return {
      loading: false,
      adding: false,
      creator: null,
      members: [],
      assignableRoles: ['Setter', 'Verifier'],
      newMember: { username: '', role: 'Setter' },
      switching: null,
      inviting: false,
      copiedRole: '',
      copiedTimer: null,
      openInvites: {}
    }
  },
  computed: {
    ...mapGetters(['canManagePrep']),
    contestID () {
      return this.$route.params.contestID
    },
    openInviteCount () {
      return Object.values(this.openInvites).reduce((sum, count) => sum + count, 0)
    }
  },
  mounted () {
    this.load()
  },
  beforeUnmount () {
    clearTimeout(this.copiedTimer)
  },
  methods: {
    roleLabel (role) {
      return this.$t(`m.Prep_Role_${role}`)
    },
    otherRole (role) {
      return role === 'Setter' ? 'Verifier' : 'Setter'
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
      if (this.canManagePrep) this.loadInvites()
    },
    async loadInvites () {
      try {
        const res = await api.getPrepInvites(this.contestID)
        this.openInvites = res.data.data.open || {}
      } catch (_) {
        this.openInvites = {}
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
    async toggleRole (member) {
      const role = this.otherRole(member.role)
      this.switching = member.id
      try {
        await api.updatePrepMember(this.contestID, member.user.id, role)
        member.role = role
      } catch (_) {
        await this.load()
      } finally {
        this.switching = null
      }
    },
    async copyInvite () {
      const role = this.newMember.role
      this.inviting = true
      try {
        // Each click mints a new single-use link; the token is never shown again.
        const res = await api.createPrepInvite(this.contestID, role)
        const link = inviteLink(res.data.data.token)
        if (await copyText(link)) {
          clearTimeout(this.copiedTimer)
          this.copiedRole = role
          this.copiedTimer = setTimeout(() => { this.copiedRole = '' }, COPIED_MS)
        } else {
          this.$Modal.info({ title: this.$t('m.Prep_Invite_Link'), content: link })
        }
        this.loadInvites()
      } catch (_) {
        // The API client already shows the error.
      } finally {
        this.inviting = false
      }
    },
    revokeInvites () {
      this.$confirm(this.$t('m.Prep_Invite_Revoke_Confirm'), this.$t('m.Prep_Invite_Link'), {
        type: 'warning'
      }).then(async () => {
        await api.revokePrepInvites(this.contestID)
        await this.loadInvites()
      }).catch(() => {})
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
.prep-member-form .el-button + .invite-button { margin-left: 0; }
.prep-member-user { flex: 0 1 320px; min-width: 200px; :deep(.el-autocomplete) { width: 100%; } }
.prep-member-role { width: 140px; }
.suggestion-name { color: var(--color-text); }
.suggestion-real-name { margin-left: 8px; color: var(--color-text-faint); font-size: 12px; }

/* Both labels share one grid cell, so the button keeps its width while they swap. */
.invite-button {
  display: inline-grid;
  height: 32px;
  align-items: center;
  overflow: hidden;
  padding: 0 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
  color: var(--color-text);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
  transition: background-color .25s ease, border-color .25s ease, color .25s ease;
  &:hover:not(:disabled), &:focus-visible { border-color: var(--line-strong); background: var(--bg-hover); }
  &.is-busy { cursor: wait; }
  &.is-copied { border-color: rgba(15, 123, 108, .32); background: var(--tag-tools-bg); color: var(--cat-tools); }
}
.invite-label {
  display: inline-flex;
  grid-area: 1 / 1;
  align-items: center;
  justify-content: center;
  gap: 6px;
  white-space: nowrap;
  transition: opacity .25s ease, transform .3s cubic-bezier(.2, .8, .2, 1);
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 15px; height: 15px; }
}
.invite-done { opacity: 0; transform: translateY(70%); }
.is-copied .invite-idle { opacity: 0; transform: translateY(-70%); }
.is-copied .invite-done { opacity: 1; transform: none; }
.invite-revoke {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-text-faint);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  &:hover, &:focus-visible { color: var(--oj-danger); }
}

.prep-member-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  th, td { padding: 10px 12px; border-bottom: 1px solid var(--color-border); text-align: left; vertical-align: middle; }
  th { color: var(--color-text-muted); font-weight: 600; }
  .actions-column { width: 90px; text-align: right; }
}

/* Role capsules match the review leaderboard chips. */
.role-pill {
  display: inline-flex;
  height: 24px;
  align-items: center;
  gap: 4px;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  transition: background-color .25s ease, color .25s ease, box-shadow .2s ease, opacity .2s ease;
}
.role-creator { background: var(--tag-recommend-bg); color: var(--cat-recommend); }
.role-setter { background: var(--tag-course-bg); color: var(--cat-course); }
.role-verifier { background: var(--tag-kaggle-bg); color: var(--cat-kaggle); }
.role-pill.is-toggle {
  cursor: pointer;
  &:hover, &:focus-visible { box-shadow: 0 0 0 1px currentColor inset; }
  &.is-busy { cursor: wait; opacity: .6; }
}
.role-swap {
  display: inline-flex;
  max-width: 0;
  overflow: hidden;
  opacity: 0;
  transition: max-width .2s ease, opacity .2s ease;
  :deep(svg) { width: 12px; height: 12px; }
}
.role-pill.is-toggle:hover .role-swap,
.role-pill.is-toggle:focus-visible .role-swap { max-width: 14px; opacity: .8; }

@media (prefers-reduced-motion: reduce) {
  .invite-label, .role-pill, .role-swap { transition: none; }
}
</style>
