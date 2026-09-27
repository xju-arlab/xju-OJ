<template>
  <section v-if="recent.length" class="contest-announcement-banner" role="region"
           :aria-label="$t('m.Contest_Announcements')" aria-live="polite">
    <div class="announcement-header">
      <span class="announcement-icon" aria-hidden="true"><Icon type="megaphone" /></span>
      <strong>{{$t('m.Contest_Announcements')}}</strong>
      <router-link :to="{ name: 'contest-announcement-list', params: { contestID: contestId } }">
        {{$t('m.View_All_Contest_Announcements')}}
      </router-link>
    </div>
    <div class="announcement-list">
      <article v-for="announcement in recent" :key="announcement.id" class="announcement-item">
        <h2>{{announcement.title}}</h2>
        <p v-if="announcement.contentText">{{announcement.contentText}}</p>
      </article>
    </div>
  </section>
</template>

<script>
  import api from '@oj/api'
  import { activeContestAnnouncements, ANNOUNCEMENT_VISIBLE_MS } from '@oj/contestAnnouncements.mjs'

  function plainText (html) {
    const template = document.createElement('template')
    template.innerHTML = (html || '').replace(/<br\s*\/?>|<\/(?:p|div|li|h[1-6])>/gi, ' ')
    return (template.content.textContent || '').replace(/\s+/g, ' ').trim()
  }

  export default {
    name: 'ContestAnnouncementBanner',
    props: {
      contestId: { type: [String, Number], required: true }
    },
    data () {
      return {
        announcements: [],
        recent: [],
        clockOffsetMs: 0,
        pollTimer: null,
        expiryTimer: null,
        inFlight: false,
        active: false
      }
    },
    mounted () {
      this.active = true
      document.addEventListener('visibilitychange', this.onVisibilityChange)
      this.poll()
    },
    beforeUnmount () {
      this.active = false
      document.removeEventListener('visibilitychange', this.onVisibilityChange)
      clearTimeout(this.pollTimer)
      clearTimeout(this.expiryTimer)
    },
    methods: {
      nowMs () {
        return Date.now() + this.clockOffsetMs
      },
      updateRecent () {
        clearTimeout(this.expiryTimer)
        const now = this.nowMs()
        this.recent = activeContestAnnouncements(this.announcements, now).map(announcement => ({
          ...announcement,
          contentText: plainText(announcement.content)
        }))
        if (!this.recent.length) return
        const nextExpiry = Math.min(...this.recent.map(item => Date.parse(item.create_time) + ANNOUNCEMENT_VISIBLE_MS))
        this.expiryTimer = setTimeout(this.updateRecent, Math.max(1, nextExpiry - now + 1))
      },
      schedulePoll () {
        clearTimeout(this.pollTimer)
        // Spread clients across time so announcements do not cause synchronized requests.
        this.pollTimer = setTimeout(this.poll, 30000 + Math.floor(Math.random() * 10000))
      },
      async poll () {
        clearTimeout(this.pollTimer)
        if (!this.active) return
        if (document.hidden) {
          this.schedulePoll()
          return
        }
        if (this.inFlight) return
        this.inFlight = true
        try {
          const response = await api.pollContestAnnouncementList(this.contestId)
          if (!this.active || !Array.isArray(response.data.data)) return
          const serverTime = Date.parse(response.headers?.date)
          if (Number.isFinite(serverTime)) this.clockOffsetMs = serverTime - Date.now()
          this.announcements = response.data.data
          this.updateRecent()
        } catch (_) {
          // Background polling must never interrupt reading or submitting.
        } finally {
          this.inFlight = false
          if (this.active) this.schedulePoll()
        }
      },
      onVisibilityChange () {
        if (document.hidden) return
        this.updateRecent()
        this.poll()
      }
    }
  }
</script>

<style scoped lang="less">
  .contest-announcement-banner {
    margin-bottom: 18px;
    overflow: hidden;
    border: 1px solid #d5a342;
    border-radius: var(--radius-md);
    background: #fffaf0;
    color: var(--color-text);
  }
  .announcement-header {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 11px 16px;
    border-bottom: 1px solid #f0dfb9;
  }
  .announcement-icon { display: inline-flex; color: #a86a08; }
  .announcement-header strong { font-size: 14px; }
  .announcement-header a { margin-left: auto; font-size: 12px; white-space: nowrap; }
  .announcement-list { max-height: 210px; overflow-y: auto; }
  .announcement-item { padding: 10px 16px; }
  .announcement-item + .announcement-item { border-top: 1px solid #f0dfb9; }
  .announcement-item h2 { margin: 0; font-size: 14px; font-weight: 700; line-height: 1.4; overflow-wrap: anywhere; }
  .announcement-item p { margin: 4px 0 0; font-size: 13px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }
  @media (max-width: 620px) {
    .announcement-header { flex-wrap: wrap; }
    .announcement-header a { margin-left: 0; }
  }
</style>
