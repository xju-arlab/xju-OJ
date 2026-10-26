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
      <el-button type="primary" native-type="submit" :loading="adding">{{ $t('m.Prep_Add_Member') }}</el-button>
      <button type="button" class="tool-button" @click="openLinks">
        <Icon type="bars" />
        <span>{{ $t('m.Prep_Manage_Links') }}</span>
        <span v-if="openInviteCount" class="tool-count">{{ openInviteCount }}</span>
      </button>
      <button type="button"
              :class="['tool-button', 'invite-button', { 'is-copied': copied, 'is-busy': inviting }]"
              :disabled="inviting"
              @click="copyInvite">
        <span class="invite-label invite-idle" :aria-hidden="copied ? 'true' : 'false'">
          <Icon type="link" />{{ $t('m.Prep_Invite_Link') }}
        </span>
        <span class="invite-label invite-done" :aria-hidden="copied ? 'false' : 'true'" role="status">
          <Icon type="check" />{{ copied ? $t('m.Prep_Invite_Copied') : '' }}
        </span>
      </button>
    </form>

    <table class="prep-member-table">
      <thead>
        <tr>
          <th>{{ $t('m.Username') }}</th>
          <th>{{ $t('m.Prep_Real_Name') }}</th>
          <th>{{ $t('m.Prep_Role') }}</th>
          <th v-if="canManagePrep" class="actions-column"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="creator">
          <td><router-link :to="userHome(creator.username)">{{ creator.username }}</router-link></td>
          <td class="real-name">{{ creator.real_name || '—' }}</td>
          <td><span class="role-pill role-creator">{{ roleLabel('Creator') }}</span></td>
          <td v-if="canManagePrep"></td>
        </tr>
        <tr v-for="member in members" :key="member.id">
          <td><router-link :to="userHome(member.user.username)">{{ member.user.username }}</router-link></td>
          <td class="real-name">{{ member.user.real_name || '—' }}</td>
          <td><span :class="['role-pill', `role-${member.role.toLowerCase()}`]">{{ roleLabel(member.role) }}</span></td>
          <td v-if="canManagePrep" class="actions-column">
            <el-button text type="danger" size="small" @click="removeMember(member)">{{ $t('m.Prep_Remove') }}</el-button>
          </td>
        </tr>
        <tr v-if="!loading && !members.length">
          <td :colspan="canManagePrep ? 4 : 3" class="prep-empty">{{ $t('m.Prep_No_Members') }}</td>
        </tr>
      </tbody>
    </table>

    <LegacyDialog v-if="canManagePrep" :title="$t('m.Prep_Manage_Links')" width="680px"
                  :visible="linksVisible" @update:visible="linksVisible = $event">
      <table v-if="invites.length" class="invite-table">
        <thead>
          <tr>
            <th>{{ $t('m.Status') }}</th>
            <th>{{ $t('m.Prep_Invite_Created') }}</th>
            <th>{{ $t('m.Prep_Invite_Detail') }}</th>
            <th class="actions-column"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="invite in invites" :key="invite.id" :class="`is-${invite.status}`">
            <td><span :class="['status-dot', `is-${invite.status}`]">{{ $t(`m.Prep_Invite_Status_${invite.status}`) }}</span></td>
            <td class="muted">{{ shortTime(invite.create_time) }}</td>
            <td class="muted">{{ inviteDetail(invite) }}</td>
            <td class="actions-column">
              <el-button v-if="invite.status === 'active'" text type="danger" size="small"
                         :loading="revokingId === invite.id" @click="revokeInvite(invite)">
                {{ $t('m.Prep_Invite_Revoke_One') }}
              </el-button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="invite-empty">{{ invitesLoading ? $t('m.Loading') : $t('m.Prep_No_Invites') }}</p>
      <template #footer>
        <div class="invite-footer">
          <el-button v-if="openInviteCount" text type="danger" @click="revokeAll">{{ $t('m.Prep_Invite_Revoke_All') }}</el-button>
          <span class="invite-footer-spacer"></span>
          <el-button @click="linksVisible = false">{{ $t('m.Close') }}</el-button>
        </div>
      </template>
    </LegacyDialog>
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
      newMember: { username: '' },
      inviting: false,
      copied: false,
      copiedTimer: null,
      openInvites: {},
      invites: [],
      invitesLoading: false,
      linksVisible: false,
      revokingId: null
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
    userHome (username) {
      return { name: 'user-home', query: { username } }
    },
    shortTime (value) {
      return value ? this.$filters.localtime(value, 'MM-DD HH:mm') : '—'
    },
    inviteDetail (invite) {
      if (invite.status === 'used') return this.$t('m.Prep_Invite_Joined', { user: invite.used_by || '—' })
      if (invite.status === 'revoked') return this.$t('m.Prep_Invite_Revoked_At', { time: this.shortTime(invite.revoked_time) })
      if (invite.status === 'expired') return this.$t('m.Prep_Invite_Expired_At', { time: this.shortTime(invite.expire_time) })
      return this.$t('m.Prep_Invite_Expires', { time: this.shortTime(invite.expire_time) })
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
      this.invitesLoading = true
      try {
        const res = await api.getPrepInvites(this.contestID)
        this.openInvites = res.data.data.open || {}
        this.invites = res.data.data.invites || []
      } catch (_) {
        this.openInvites = {}
      } finally {
        this.invitesLoading = false
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
        await api.addPrepMember(this.contestID, username)
        this.newMember.username = ''
        await this.load()
      } catch (_) {
        // The API client already shows the error.
      } finally {
        this.adding = false
      }
    },
    async copyInvite () {
      this.inviting = true
      try {
        // Each click mints a new single-use organizer link; the token is never shown again.
        const res = await api.createPrepInvite(this.contestID)
        const link = inviteLink(res.data.data.token)
        if (await copyText(link)) {
          clearTimeout(this.copiedTimer)
          this.copied = true
          this.copiedTimer = setTimeout(() => { this.copied = false }, COPIED_MS)
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
    openLinks () {
      this.linksVisible = true
      this.loadInvites()
    },
    async revokeInvite (invite) {
      this.revokingId = invite.id
      try {
        await api.revokePrepInvites(this.contestID, invite.id)
        await this.loadInvites()
      } catch (_) {
        // The API client already shows the error.
      } finally {
        this.revokingId = null
      }
    },
    revokeAll () {
      this.$confirm(this.$t('m.Prep_Invite_Revoke_Confirm'), this.$t('m.Prep_Manage_Links'), {
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
.prep-member-form .el-button + .tool-button { margin-left: 0; }
.prep-member-user { flex: 0 1 320px; min-width: 200px; :deep(.el-autocomplete) { width: 100%; } }
.suggestion-name { color: var(--color-text); }
.suggestion-real-name { margin-left: 8px; color: var(--color-text-faint); font-size: 12px; }

.tool-button {
  display: inline-flex;
  height: 32px;
  align-items: center;
  gap: 6px;
  padding: 0 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
  color: var(--color-text);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
  transition: background-color .25s ease, border-color .25s ease, color .25s ease;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 15px; height: 15px; }
  &:hover:not(:disabled), &:focus-visible { border-color: var(--line-strong); background: var(--bg-hover); }
}
.tool-count {
  display: inline-flex;
  min-width: 18px;
  height: 18px;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--tag-tools-bg);
  color: var(--cat-tools);
  font-size: 11px;
  font-weight: 650;
}

/* Both labels share one grid cell, so the button keeps its width while they swap. */
.invite-button {
  display: inline-grid;
  overflow: hidden;
  &.is-busy { cursor: wait; }
  &.is-copied, &.is-copied:hover:not(:disabled) { border-color: rgba(15, 123, 108, .32); background: var(--tag-tools-bg); color: var(--cat-tools); }
}
.invite-label {
  display: inline-flex;
  grid-area: 1 / 1;
  align-items: center;
  justify-content: center;
  gap: 6px;
  white-space: nowrap;
  transition: opacity .25s ease, transform .3s cubic-bezier(.2, .8, .2, 1);
}
.invite-done { opacity: 0; transform: translateY(70%); }
.is-copied .invite-idle { opacity: 0; transform: translateY(-70%); }
.is-copied .invite-done { opacity: 1; transform: none; }

.prep-member-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  th, td { padding: 10px 12px; border-bottom: 1px solid var(--color-border); text-align: left; vertical-align: middle; }
  th { color: var(--color-text-muted); font-weight: 600; }
  .actions-column { width: 90px; text-align: right; }
  .real-name { color: var(--color-text); }
}

/* Role capsules match the review leaderboard chips. */
.role-pill {
  display: inline-flex;
  height: 24px;
  align-items: center;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  transition: background-color .25s ease, color .25s ease, box-shadow .2s ease, opacity .2s ease;
  &.is-small { height: 22px; padding: 0 8px; font-size: 11px; }
}
.role-creator { background: var(--tag-recommend-bg); color: var(--cat-recommend); }
.role-organizer { background: var(--tag-course-bg); color: var(--cat-course); }

.invite-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  th, td { padding: 9px 10px; border-bottom: 1px solid var(--color-border); text-align: left; vertical-align: middle; white-space: nowrap; }
  th { color: var(--color-text-muted); font-weight: 600; }
  tr.is-used, tr.is-expired, tr.is-revoked { color: var(--color-text-muted); }
  .muted { color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
  .actions-column { width: 70px; text-align: right; }
}
.status-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  &::before { width: 6px; height: 6px; border-radius: 50%; background: currentColor; content: ""; }
  &.is-active { color: var(--cat-tools); }
  &.is-used { color: var(--cat-kaggle); }
  &.is-expired, &.is-revoked { color: var(--color-text-faint); }
}
.invite-empty { padding: 28px 0; color: var(--color-text-faint); text-align: center; }
.invite-footer { display: flex; align-items: center; gap: 8px; }
.invite-footer-spacer { flex: 1; }

@media (prefers-reduced-motion: reduce) {
  .invite-label, .role-pill { transition: none; }
}
</style>
