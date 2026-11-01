<template>
  <section class="arena-waiting" aria-label="赛前等待" @mousemove="wake" @touchstart.passive="wake">
    <div class="arena-waiting-stage" :style="{ transform: `translate(-50%, -50%) scale(${scale})` }">
      <article v-for="(theme, index) in THEMES" :key="theme.id" :class="['poster', { 'is-active': index === current }]"
               :style="themeStyle(theme)" :aria-hidden="index !== current">
        <img class="poster-art" :src="theme.art" alt="" decoding="async">
        <div class="poster-veil"></div>
        <img :class="['poster-logo', `is-${theme.contest.toLowerCase()}`]" :src="LOGOS[theme.contest]" :alt="theme.contest">
        <p class="poster-kicker">{{ theme.contest }} / PROGRAMMING CONTEST</p>
        <h2 class="poster-title" :style="{ fontSize: `${titleSizes[theme.id] || 112}px` }">
          <span v-for="line in theme.title" :key="line">{{ line }}</span>
        </h2>
        <p class="poster-subtitle">{{ theme.subtitle }}</p>
        <p class="poster-tag">{{ theme.tag }}</p>
        <div class="poster-fade"></div>
        <div class="poster-band"></div>
        <div class="poster-crest"><img :src="CREST" alt="新疆大学"></div>
        <div class="poster-team">
          <strong :style="{ fontSize: `${nameSize}px` }">{{ team.name }}</strong>
          <span class="poster-kind">{{ team.kind }}</span>
        </div>
        <p class="poster-members">{{ team.members.join('  ·  ') || '—' }}</p>
        <p class="poster-contest">{{ contestLine }}</p>
        <p class="poster-status"><i aria-hidden="true"></i>{{ statusLabel }}</p>
        <p class="poster-clock">{{ clock }}</p>
        <p class="poster-school">XINJIANG UNIVERSITY</p>
      </article>
    </div>
    <div :class="['arena-waiting-controls', { 'is-idle': idle }]">
      <button v-for="(theme, index) in THEMES" :key="theme.id" type="button"
              :class="['arena-waiting-dot', { 'is-active': index === current }]"
              :aria-label="theme.label" @click="show(index)"></button>
      <span class="arena-waiting-divider" aria-hidden="true"></span>
      <button type="button" class="arena-waiting-action" @click="toggleFullscreen">{{ fullscreen ? '退出全屏' : '全屏' }}</button>
      <button v-if="viewer === 'team'" type="button" class="arena-waiting-action" @click="logout">退出登录</button>
      <button v-else type="button" class="arena-waiting-action" @click="enter">进入比赛页</button>
    </div>
  </section>
</template>
<script>
  import moment from 'moment'
  import api from '@oj/api'
  import { USER_TYPE } from '@/utils/constants'
  import icpc01 from '@/assets/arena-waiting/icpc01.webp'
  import icpc02 from '@/assets/arena-waiting/icpc02.webp'
  import icpc03 from '@/assets/arena-waiting/icpc03.webp'
  import icpc04 from '@/assets/arena-waiting/icpc04.webp'
  import ccpc01 from '@/assets/arena-waiting/ccpc01.webp'
  import ccpc02 from '@/assets/arena-waiting/ccpc02.webp'
  import icpcLogo from '@/assets/arena-waiting/icpc-logo.webp'
  import ccpcLogo from '@/assets/arena-waiting/ccpc-logo.webp'
  import xjuCrest from '@/assets/arena-waiting/xju-crest.webp'

  // The six waiting posters: one 2560×1440 layout over each illustration, with
  // the colours each artwork was designed with.
  const THEMES = [
    { id: 'icpc01', label: 'ICPC · 晴空启程', contest: 'ICPC', art: icpc01, title: ['READY', 'TO CODE.'], subtitle: '热爱算法 · 即刻出发', tag: 'LET THE IDEAS TAKE FLIGHT', ink: '#FFFFFF', veil: '#144CAB', veilOpacity: 0.58, band: '#F7FAFF', text: '#112A4D', muted: '#6A7B94', accent: '#3478E7', rule: '#CCD9EF', pill: '#E6EEFF' },
    { id: 'icpc02', label: 'ICPC · 纯蓝协作', contest: 'ICPC', art: icpc02, title: ['THINK.', 'SOLVE.'], subtitle: '并肩思考 · 一同突破', tag: 'THREE MINDS. ONE MISSION.', ink: '#FFFFFF', veil: '#4871CA', veilOpacity: 0.18, band: '#F6F8FF', text: '#233F7C', muted: '#7C8AAC', accent: '#6683D6', rule: '#CED9F0', pill: '#E7EDFE' },
    { id: 'icpc03', label: 'ICPC · 星河逐梦', contest: 'ICPC', art: icpc03, title: ['CHASE', 'THE STARS.'], subtitle: '下一题，一起解', tag: 'EVERY SOLUTION IS A NEW STAR', ink: '#FAF7FF', veil: '#111844', veilOpacity: 0.63, band: '#171B3E', text: '#F5F1FF', muted: '#B1ACD2', accent: '#C6B4FA', rule: '#424362', pill: '#363255' },
    { id: 'icpc04', label: 'ICPC · 暖阳集结', contest: 'ICPC', art: icpc04, title: ['HELLO,', 'ICPC.'], subtitle: '把热爱写进每一次提交', tag: 'GOOD IDEAS. GREAT TEAMWORK.', ink: '#74311C', veil: '#FFE5C5', veilOpacity: 0.12, band: '#FFFAF2', text: '#4E2B24', muted: '#9B7B70', accent: '#D46B42', rule: '#E7CFC0', pill: '#F9E5D9' },
    { id: 'ccpc01', label: 'CCPC · 青绿同频', contest: 'CCPC', art: ccpc01, title: ['CODE', 'IN SYNC.'], subtitle: '同频思考 · 默契作答', tag: 'FIND THE PATTERN. SHARE THE JOY.', ink: '#135948', veil: '#E2FFF2', veilOpacity: 0.10, band: '#F5FBF7', text: '#173F35', muted: '#6D8A7E', accent: '#228F6B', rule: '#C9E0D4', pill: '#E0F1E8' },
    { id: 'ccpc02', label: 'CCPC · 锦色山河', contest: 'CCPC', art: ccpc02, title: ['SOLVE', 'TOGETHER.'], subtitle: '一同解题 · 一路向前', tag: 'LET CURIOSITY LEAD THE WAY', ink: '#7E342D', veil: '#FFF2DF', veilOpacity: 0.83, band: '#FFFAF2', text: '#5F302B', muted: '#977F6F', accent: '#B85243', rule: '#E4D2BE', pill: '#F5E5D8' }
  ]
  const LOGOS = { ICPC: icpcLogo, CCPC: ccpcLogo }
  const STAGE = { width: 2560, height: 1440 }
  const TITLE_FONT = '700 124px "Avenir Next", Geist, "Segoe UI", sans-serif'
  const NAME_FONT = '700 72px "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif'
  const SLIDE_MS = 8000
  const IDLE_MS = 3000
  const PREVIEW_TEAM = { name: '队伍名称', kind: '正式队', members: ['队员一', '队员二', '队员三'] }

  function rgba (hex, alpha) {
    const value = parseInt(hex.slice(1), 16)
    return `rgba(${value >> 16}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`
  }

  function measure (font, text) {
    const context = document.createElement('canvas').getContext('2d')
    context.font = font
    return context.measureText(text).width
  }

  export default {
    name: 'ContestWaiting',
    data () {
      return {
        THEMES, LOGOS, CREST: xjuCrest,
        contest: null, viewer: '', current: 0, scale: 1, now: Date.now(), offset: 0,
        titleSizes: {}, nameSize: 72, idle: false, fullscreen: false, timers: []
      }
    },
    computed: {
      contestID () { return String(this.$route.params.contestID) },
      team () {
        const team = this.$store.state.user.profile.team
        if (this.viewer !== 'team' || !team) return PREVIEW_TEAM
        return { name: team.name, kind: team.star ? '打星队' : '正式队', members: team.members || [] }
      },
      startsAt () { return this.contest ? Date.parse(this.contest.start_time) : 0 },
      remaining () { return Math.max(0, this.startsAt - this.now) },
      statusLabel () { return this.remaining > 0 ? '赛前等待 · 距离开始' : '比赛已开始' },
      clock () {
        const total = Math.floor(this.remaining / 1000)
        const hours = Math.floor(total / 3600)
        return [hours, Math.floor(total % 3600 / 60), total % 60].map(part => String(part).padStart(2, '0')).join(':')
      },
      contestLine () {
        if (!this.contest) return ''
        return `${this.contest.title} · ${moment(this.contest.start_time).format('M月D日 HH:mm')} 开赛`
      }
    },
    watch: {
      team: { immediate: true, handler () { this.fitName() } }
    },
    async mounted () {
      this.fit()
      window.addEventListener('resize', this.fit)
      document.addEventListener('fullscreenchange', this.syncFullscreen)
      try {
        this.contest = (await api.getContest(this.contestID)).data.data
      } catch (_) {
        this.$router.replace({ name: 'contest-arena', params: { contestID: this.contestID } })
        return
      }
      try { await this.$store.dispatch('getProfile') } catch (_) {}
      if (!this.admit()) return
      this.syncClock(this.contest)
      this.fitTitles()
      this.wake()
      const motion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
      this.timers.push(setInterval(this.tick, 1000))
      this.timers.push(setInterval(() => this.show(this.current + 1), motion ? SLIDE_MS * 2 : SLIDE_MS))
      // A changed start time reaches the page within a minute.
      this.timers.push(setInterval(this.refresh, 60000))
    },
    beforeUnmount () {
      this.timers.forEach(clearInterval)
      clearTimeout(this.idleTimer)
      window.removeEventListener('resize', this.fit)
      document.removeEventListener('fullscreenchange', this.syncFullscreen)
    },
    methods: {
      // Teams of this contest wait here until the start; contest admins may preview
      // it at any time; everyone else signs in first.
      admit () {
        const { user, team } = this.$store.state.user.profile
        const admin = user && (this.contest.created_by.id === user.id || user.admin_type === USER_TYPE.SUPER_ADMIN)
        if (team && String(team.contest_id) === this.contestID) {
          if (this.contest.status !== '1') {
            this.enter()
            return false
          }
          this.viewer = 'team'
          return true
        }
        if (admin) {
          this.viewer = 'admin'
          return true
        }
        this.$router.replace({ name: 'contest-arena', params: { contestID: this.contestID } })
        return false
      },
      enter () {
        this.$router.replace(`/arena/${this.contestID}/`)
      },
      syncClock (contest) {
        // The countdown follows the server clock, not the device's.
        if (contest.now) this.offset = Date.parse(contest.now) - Date.now()
        this.now = Date.now() + this.offset
      },
      tick () {
        this.now = Date.now() + this.offset
        if (this.viewer === 'team' && this.remaining === 0 && !this.checking) this.refresh()
      },
      async refresh () {
        this.checking = true
        try {
          const contest = (await api.getContest(this.contestID)).data.data
          this.contest = contest
          this.syncClock(contest)
          if (this.viewer === 'team' && contest.status !== '1') this.enter()
        } catch (_) {
          // Keep the current countdown; the next tick tries again.
        } finally {
          setTimeout(() => { this.checking = false }, 5000)
        }
      },
      show (index) {
        this.current = (index + THEMES.length) % THEMES.length
      },
      fit () {
        this.scale = Math.min(window.innerWidth / STAGE.width, window.innerHeight / STAGE.height)
      },
      async fitTitles () {
        // Each headline keeps to the quiet left side of its artwork, 655 px wide at most.
        try { await document.fonts.ready } catch (_) {}
        const sizes = {}
        for (const theme of THEMES) {
          const widest = Math.max(...theme.title.map(line => measure(TITLE_FONT, line)))
          sizes[theme.id] = Math.min(124, Math.floor(655 / widest * 124))
        }
        this.titleSizes = sizes
      },
      fitName () {
        const width = measure(NAME_FONT, this.team.name)
        this.nameSize = width > 1320 ? Math.max(36, Math.floor(72 * 1320 / width)) : 72
      },
      themeStyle (theme) {
        return {
          '--ink': theme.ink, '--band': theme.band, '--text': theme.text, '--muted': theme.muted,
          '--accent': theme.accent, '--rule': theme.rule, '--pill': theme.pill,
          '--veil': `linear-gradient(90deg, ${rgba(theme.veil, theme.veilOpacity)} 0, ${rgba(theme.veil, theme.veilOpacity)} 420px, ${rgba(theme.veil, 0)} 1220px)`,
          '--fade': `linear-gradient(180deg, ${rgba(theme.band, 0)} 0, ${rgba(theme.band, 0.15)} 25%, ${rgba(theme.band, 0.37)} 50%, ${rgba(theme.band, 0.63)} 75%, ${rgba(theme.band, 0.92)} 100%)`
        }
      },
      wake () {
        this.idle = false
        clearTimeout(this.idleTimer)
        this.idleTimer = setTimeout(() => { this.idle = true }, IDLE_MS)
      },
      toggleFullscreen () {
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
        else document.documentElement.requestFullscreen().catch(() => {})
      },
      syncFullscreen () {
        this.fullscreen = Boolean(document.fullscreenElement)
      },
      async logout () {
        try { await api.logout() } catch (_) {}
        this.$store.dispatch('clearProfile')
        this.$router.replace({ name: 'contest-arena', params: { contestID: this.contestID } })
      }
    }
  }
</script>
<style scoped lang="less">
  .arena-waiting { position: fixed; z-index: 2000; inset: 0; overflow: hidden; background: #0b0f19; }
  .arena-waiting-stage { position: absolute; top: 50%; left: 50%; width: 2560px; height: 1440px; transform-origin: center; }

  // Every position below is in the 2560×1440 poster space.
  .poster { position: absolute; inset: 0; overflow: hidden; background: var(--band); opacity: 0; transition: opacity 1.2s ease; }
  .poster.is-active { opacity: 1; }
  .poster > * { position: absolute; margin: 0; }
  .poster-art { top: 0; left: 0; width: 2560px; height: 1080px; object-fit: cover; }
  .poster-veil { top: 0; left: 0; width: 1220px; height: 1080px; background: var(--veil); }
  .poster-logo { left: 214px; top: 151px; transform: translate(-50%, -50%); object-fit: contain; }
  .poster-logo.is-icpc { width: 210px; height: 144px; }
  .poster-logo.is-ccpc { width: 132px; height: 132px; }
  .poster-kicker, .poster-tag, .poster-title, .poster-school { font-family: "Avenir Next", Geist, "Segoe UI", sans-serif; font-weight: 700; }
  .poster-kicker { left: 96px; top: 282px; color: var(--ink); font-size: 21px; letter-spacing: 3.8px; line-height: 1; }
  .poster-title { left: 88px; top: 340px; display: grid; color: var(--ink); line-height: 140px; letter-spacing: 0; white-space: nowrap; }
  .poster-subtitle { left: 96px; top: 668px; color: var(--ink); font: 400 32px/1.2 "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif; }
  .poster-subtitle::before { content: ""; position: absolute; top: -32px; left: 0; width: 76px; height: 4px; background: var(--ink); }
  .poster-tag { left: 96px; top: 860px; color: var(--ink); font-size: 17px; letter-spacing: 2.4px; line-height: 1; }
  .poster-fade { top: 870px; left: 0; width: 2560px; height: 210px; background: var(--fade); }
  .poster-band { top: 1080px; left: 0; width: 2560px; height: 360px; background: var(--band); border-top: 4px solid var(--accent); transform: translateY(-2px); }
  .poster-crest { left: 90px; top: 960px; display: grid; width: 240px; height: 240px; box-sizing: border-box; place-items: center; border: 3px solid var(--rule); border-radius: 50%; background: #fff; }
  .poster-crest img { width: 222px; height: 222px; }
  .poster-team, .poster-members, .poster-contest, .poster-status { font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif; }
  .poster-team { left: 384px; top: 985px; display: flex; height: 72px; align-items: center; gap: 34px; color: var(--text); white-space: nowrap; }
  .poster-team strong { font-weight: 700; line-height: 1; }
  .poster-kind { display: inline-flex; height: 60px; align-items: center; padding: 0 22px; border-radius: 13px; background: var(--pill); color: var(--accent); font-size: 30px; }
  .poster-members { left: 384px; top: 1176px; color: var(--text); font-size: 44px; line-height: 1.2; white-space: pre; }
  .poster-contest { left: 384px; top: 1302px; max-width: 1500px; overflow: hidden; color: var(--muted); font-size: 28px; line-height: 1.2; text-overflow: ellipsis; white-space: nowrap; }
  .poster-status { right: 96px; top: 1124px; display: flex; align-items: center; gap: 16px; color: var(--muted); font-size: 32px; line-height: 1.2; }
  .poster-status i { width: 16px; height: 16px; border-radius: 50%; background: var(--accent); }
  .poster-clock { right: 92px; top: 1172px; color: var(--text); font: 600 92px/1.1 "JetBrains Mono", "SF Mono", Menlo, monospace; font-variant-numeric: tabular-nums; letter-spacing: 2px; }
  .poster-school { right: 96px; top: 1314px; color: var(--muted); font-size: 23px; line-height: 1; }

  .arena-waiting-controls { position: absolute; bottom: 18px; left: 50%; display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 999px; background: rgba(15, 18, 30, .55); transform: translateX(-50%); transition: opacity .4s ease; backdrop-filter: blur(6px); }
  .arena-waiting-controls.is-idle { opacity: 0; pointer-events: none; }
  .arena-waiting-dot { width: 9px; height: 9px; padding: 0; border: 0; border-radius: 50%; background: rgba(255, 255, 255, .45); cursor: pointer; }
  .arena-waiting-dot.is-active { width: 22px; border-radius: 999px; background: #fff; }
  .arena-waiting-divider { width: 1px; height: 14px; margin: 0 2px; background: rgba(255, 255, 255, .3); }
  .arena-waiting-action { padding: 2px 6px; border: 0; background: none; color: rgba(255, 255, 255, .85); font-size: 12px; white-space: nowrap; cursor: pointer; }
  .arena-waiting-action:hover, .arena-waiting-action:focus-visible { color: #fff; }

  @media (prefers-reduced-motion: reduce) {
    .poster { transition: none; }
  }
</style>
