<template>
  <section class="prep-thread" :aria-label="$t('m.Prep_Feedback')">
    <header v-if="!bare" class="thread-head">
      <Icon type="chatbubble" />
      <strong>{{ $t('m.Prep_Feedback') }}</strong>
      <span v-if="openCount" class="thread-count">{{ openCount }}</span>
      <small v-if="items.length && openCount !== items.length">{{ $t('m.Prep_Feedback_Total', { count: items.length }) }}</small>
    </header>

    <TransitionGroup v-if="items.length" name="thread-item" tag="ul" class="thread-list">
      <li v-for="item in items" :key="item.id" :class="['thread-item', { 'is-resolved': item.resolved }]">
        <span class="thread-avatar" :style="{ '--person': colorFor(item.user) }">{{ initial(item.user) }}</span>
        <div class="thread-body">
          <div class="thread-meta">
            <strong>{{ nameOf(item.user) }}</strong>
            <time :datetime="item.create_time" :title="fullTime(item.create_time)">{{ shortTime(item.create_time) }}</time>
            <span v-if="item.resolved" class="thread-resolved"><Icon type="check" />{{ $t('m.Prep_Feedback_Resolved') }}</span>
            <span class="thread-actions">
              <button type="button" @click="toggle(item)">{{ item.resolved ? $t('m.Prep_Feedback_Reopen') : $t('m.Prep_Feedback_Resolve') }}</button>
              <button v-if="canDelete(item)" type="button" class="is-danger" @click="remove(item)">{{ $t('m.Delete') }}</button>
            </span>
          </div>
          <p>{{ item.content }}</p>
        </div>
      </li>
    </TransitionGroup>
    <p v-else-if="loaded" class="thread-empty">{{ $t('m.Prep_Feedback_Empty') }}</p>

    <div class="thread-composer">
      <textarea v-model="draft" rows="2" maxlength="2000" :aria-label="$t('m.Prep_Feedback')"
                :placeholder="$t('m.Prep_Feedback_Placeholder')"
                @keydown.enter.ctrl.prevent="send" @keydown.enter.meta.prevent="send"></textarea>
      <button type="button" class="thread-send" :disabled="!draft.trim() || sending" @click="send">
        <Icon :type="sending ? 'loading' : 'send'" :class="{ 'is-spinning': sending }" />
        <span>{{ $t('m.Prep_Feedback_Send') }}</span>
      </button>
    </div>
  </section>
</template>

<script>
import moment from 'moment'
import api from '@oj/api'
import { mapGetters } from '@/store/compat'
import { PREP_PLAN_CHANGED_EVENT } from '@/utils/constants'

const COLORS = ['#2383e2', '#d9730d', '#9065b0', '#0f7b6c', '#b8405e', '#b5926a', '#0b6e99', '#e03e3e']

// Remarks on one problem of a preparation contest: any member reads, writes and resolves
// them, whether setting or reviewing; authors and the creator may delete. The composer is
// not a <form> because the thread also sits inside the problem editor's form.
export default {
  name: 'PrepFeedbackThread',
  props: {
    contestId: { type: [String, Number], required: true },
    problemId: { type: [String, Number], required: true },
    // Without its own heading, e.g. inside a dialog that already has a title.
    bare: { type: Boolean, default: false }
  },
  emits: ['count'],
  data () {
    return { items: [], loaded: false, draft: '', sending: false }
  },
  computed: {
    ...mapGetters(['user', 'canManagePrep']),
    openCount () {
      return this.items.filter(item => !item.resolved).length
    }
  },
  watch: {
    problemId () {
      this.draft = ''
      this.load()
    },
    openCount (count) {
      this.$emit('count', count)
    }
  },
  mounted () {
    this.load()
    window.addEventListener(PREP_PLAN_CHANGED_EVENT, this.onRefresh)
  },
  beforeUnmount () {
    window.removeEventListener(PREP_PLAN_CHANGED_EVENT, this.onRefresh)
  },
  methods: {
    onRefresh (event) {
      if (event.detail && event.detail.remote) this.load()
    },
    async load () {
      const problemId = this.problemId
      try {
        const res = await api.getPrepFeedback(this.contestId, problemId)
        if (String(problemId) !== String(this.problemId)) return
        this.items = res.data.data || []
      } catch (_) {
        // The API client already shows the error.
      } finally {
        this.loaded = true
      }
    },
    nameOf (person) {
      return person.real_name || person.username
    },
    initial (person) {
      return Array.from(this.nameOf(person))[0].toUpperCase()
    },
    colorFor (person) {
      return COLORS[Math.abs(Number(person.id) || 0) % COLORS.length]
    },
    shortTime (value) {
      const time = moment(value)
      return time.isSame(moment(), 'day') ? time.format('HH:mm') : time.format('MM-DD HH:mm')
    },
    fullTime (value) {
      return moment(value).format('YYYY-MM-DD HH:mm:ss')
    },
    canDelete (item) {
      return this.canManagePrep || (this.user && item.user.id === this.user.id)
    },
    async send () {
      const content = this.draft.trim()
      if (!content || this.sending) return
      this.sending = true
      try {
        const res = await api.addPrepFeedback(this.contestId, this.problemId, content)
        this.items = [res.data.data, ...this.items]
        this.draft = ''
      } catch (_) {
        // The API client already shows the error.
      } finally {
        this.sending = false
      }
    },
    async toggle (item) {
      const resolved = !item.resolved
      try {
        await api.setPrepFeedbackResolved(this.contestId, item.id, resolved)
        item.resolved = resolved
      } catch (_) {
        await this.load()
      }
    },
    remove (item) {
      this.$confirm(this.$t('m.Prep_Feedback_Delete_Confirm'), this.$t('m.Delete'), { type: 'warning' }).then(async () => {
        await api.deletePrepFeedback(this.contestId, item.id)
        this.items = this.items.filter(entry => entry.id !== item.id)
      }).catch(() => {})
    }
  }
}
</script>

<style scoped lang="less">
.prep-thread { display: flex; min-width: 0; flex-direction: column; gap: 10px; }
.thread-head {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--color-text);
  font-size: 14px;
  :deep(.legacy-icon) { display: inline-flex; color: var(--color-text-muted); }
  :deep(svg) { width: 15px; height: 15px; }
  strong { font-weight: 650; }
  small { margin-left: auto; color: var(--color-text-faint); font-size: 12px; }
}
.thread-count {
  min-width: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--tag-course-bg);
  color: var(--cat-course);
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
}
.thread-list { display: flex; max-height: 360px; flex-direction: column; gap: 2px; margin: 0; padding: 0; overflow-y: auto; list-style: none; }
.thread-item {
  display: flex;
  gap: 10px;
  padding: 9px 8px;
  border-radius: 8px;
  transition: background-color .2s ease;
  &:hover { background: rgba(55, 53, 47, .035); }
  &.is-resolved p { color: var(--color-text-faint); }
  &.is-resolved .thread-avatar { opacity: .5; }
}
.thread-avatar {
  display: inline-flex;
  width: 26px;
  height: 26px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--person);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}
.thread-body { min-width: 0; flex: 1; }
.thread-meta {
  display: flex;
  min-height: 22px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  strong { color: var(--color-text); font-size: 13px; font-weight: 650; }
  time { color: var(--color-text-faint); font-variant-numeric: tabular-nums; }
}
.thread-resolved {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  color: var(--cat-tools);
  font-weight: 600;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 12px; height: 12px; }
}
.thread-actions {
  display: inline-flex;
  gap: 2px;
  margin-left: auto;
  opacity: 0;
  transition: opacity .15s ease;
  button {
    height: 22px;
    padding: 0 6px;
    border: 0;
    border-radius: 5px;
    background: transparent;
    color: var(--color-text-muted);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
    &:hover, &:focus-visible { background: rgba(55, 53, 47, .08); color: var(--color-text); outline: none; }
    &.is-danger:hover, &.is-danger:focus-visible { background: var(--tag-research-bg); color: var(--oj-danger); }
  }
}
.thread-item:hover .thread-actions, .thread-actions:focus-within { opacity: 1; }
.thread-body p { margin: 3px 0 0; color: var(--color-text); font-size: 13px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
.thread-empty { margin: 0; padding: 4px 0; color: var(--color-text-faint); font-size: 13px; }
.thread-composer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg);
  transition: border-color .2s ease, box-shadow .2s ease;
  &:focus-within { border-color: var(--line-strong); box-shadow: 0 2px 10px rgba(15, 15, 15, .05); }
  textarea {
    width: 100%;
    min-height: 44px;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--color-text);
    font: inherit;
    font-size: 13px;
    line-height: 1.6;
    resize: vertical;
    outline: none;
    &::placeholder { color: var(--color-text-faint); }
  }
}
.thread-send {
  display: inline-flex;
  height: 28px;
  align-items: center;
  align-self: flex-end;
  gap: 5px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: var(--color-text);
  color: var(--color-bg);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .2s ease;
  :deep(.legacy-icon) { display: inline-flex; }
  :deep(svg) { width: 13px; height: 13px; }
  &:disabled { cursor: default; opacity: .35; }
  .is-spinning { animation: thread-spin .9s linear infinite; }
}
@keyframes thread-spin { to { transform: rotate(360deg); } }
.thread-item-enter-active, .thread-item-leave-active { transition: opacity .25s ease, transform .3s cubic-bezier(.2, .8, .2, 1); }
.thread-item-enter-from, .thread-item-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
