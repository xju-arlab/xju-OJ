<template>
  <LegacyDialog :title="$t('m.Prep_Export_PDF')" width="min(1040px, 96vw)" top="6vh" class="prep-export-dialog"
                :visible="visible" @update:visible="$emit('update:visible', $event)">
    <div class="export-layout">
      <div class="export-form">
        <p class="export-note">{{ $t('m.Prep_Export_Note') }}</p>
        <el-form label-position="top" @submit.prevent>
          <el-form-item :label="$t('m.Prep_Export_Title')">
            <el-input v-model="form.title" maxlength="128" :placeholder="$t('m.Prep_Export_Title')"></el-input>
          </el-form-item>
          <div class="export-row">
            <el-form-item :label="$t('m.Prep_Export_Subtitle')">
              <el-input v-model="form.subtitle" maxlength="32" :placeholder="$t('m.Prep_Export_Subtitle_Placeholder')"></el-input>
            </el-form-item>
            <el-form-item :label="$t('m.Prep_Export_Date')">
              <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" format="YYYY 年 M 月 D 日"
                              style="width: 100%" :placeholder="$t('m.Prep_Export_Date_Placeholder')"></el-date-picker>
            </el-form-item>
          </div>
          <el-form-item :label="$t('m.Prep_Export_Cover')">
            <div class="cover-options" role="radiogroup" :aria-label="$t('m.Prep_Export_Cover')">
              <button v-for="option in covers" :key="option.key" type="button" role="radio"
                      :aria-checked="form.cover === option.key ? 'true' : 'false'"
                      :class="['cover-option', { 'is-active': form.cover === option.key }]"
                      @click="form.cover = option.key">
                <span class="cover-thumb">
                  <img v-if="option.image" :src="option.image" alt="" loading="lazy">
                  <Icon v-else type="file-text" />
                </span>
                <span class="cover-label">{{ $t(option.label) }}</span>
              </button>
            </div>
          </el-form-item>
        </el-form>
        <p v-if="previewProblems" class="export-warning">
          {{ $t('m.Prep_Export_Warnings_Short', { problems: previewProblems }) }}
        </p>
      </div>

      <!-- Only the pages, as tall as the form beside it. -->
      <section class="export-preview" :aria-label="$t('m.Prep_Export_Preview')">
        <PdfPages v-if="preview.blob" :source="preview.blob" @error="renderFailed" />
        <div v-if="!ready" class="preview-state">{{ $t('m.Prep_Export_Preview_Hint') }}</div>
        <div v-else-if="loading" :class="['preview-state', { 'is-over': preview.blob }]">
          <Icon type="loading" class="is-spinning" />{{ $t('m.Prep_Export_Working') }}
        </div>
        <div v-else-if="error" class="preview-state is-error">{{ error }}</div>
      </section>
    </div>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">{{ $t('m.Cancel') }}</el-button>
      <el-button type="primary" :loading="exporting" :disabled="!ready" @click="exportStatements">
        {{ $t('m.Prep_Export_Confirm') }}
      </el-button>
    </template>
  </LegacyDialog>
</template>

<script>
import api from '@oj/api'
import storage from '@/utils/storage'
import PdfPages from '@/shared/ui/PdfPages.vue'
import pointing from '@/assets/statement-covers/pointing.webp'
import handing from '@/assets/statement-covers/handing.webp'
import table from '@/assets/statement-covers/table.webp'
import balloons from '@/assets/statement-covers/balloons.webp'
import balloon from '@/assets/statement-covers/balloon.webp'

// Keys match contest/statement_pdf.py COVERS.
const COVERS = [
  { key: 'plain', label: 'm.Prep_Export_Cover_Plain', image: null },
  { key: 'pointing', label: 'm.Prep_Export_Cover_Pointing', image: pointing },
  { key: 'handing', label: 'm.Prep_Export_Cover_Handing', image: handing },
  { key: 'table', label: 'm.Prep_Export_Cover_Table', image: table },
  { key: 'balloons', label: 'm.Prep_Export_Cover_Balloons', image: balloons },
  { key: 'balloon', label: 'm.Prep_Export_Cover_Balloon', image: balloon }
]
const PREVIEW_DELAY_MS = 700

async function readError (res, fallback) {
  try {
    const payload = JSON.parse(await res.data.text())
    if (typeof payload.data === 'string') return payload.data
  } catch (_) {
    // Not JSON: keep the generic message.
  }
  return fallback
}

function problemsWithWarnings (res) {
  try {
    const warnings = JSON.parse(res.headers['x-statement-warnings'] || '[]')
    return [...new Set(warnings.map(item => item.problem).filter(Boolean))].join('、')
  } catch (_) {
    return ''
  }
}

// Typesets the whole statement PDF on the server for a live preview, one request at a time;
// exporting reuses the preview when nothing changed since.
export default {
  name: 'PrepStatementExportDialog',
  components: { PdfPages },
  props: {
    visible: { type: Boolean, default: false },
    contestId: { type: [String, Number], required: true },
    contestTitle: { type: String, default: '' }
  },
  emits: ['update:visible'],
  data () {
    return {
      covers: COVERS,
      form: { title: '', subtitle: '', date: '', cover: 'plain' },
      preview: { key: '', blob: null, filename: '', problems: '' },
      loading: false,
      rerun: false,
      error: '',
      exporting: false,
      timer: null
    }
  },
  computed: {
    ready () {
      return Boolean(this.form.title.trim() && this.form.date)
    },
    requestKey () {
      return JSON.stringify([this.form.title.trim(), this.form.subtitle.trim(), this.form.date, this.form.cover])
    },
    previewProblems () {
      return this.preview.key === this.requestKey ? this.preview.problems : ''
    }
  },
  watch: {
    visible: {
      handler (open) {
        if (open) this.open()
        else this.close()
      },
      immediate: true
    },
    requestKey () {
      if (this.visible) this.schedulePreview()
    }
  },
  beforeUnmount () {
    this.close()
  },
  methods: {
    storageKey () {
      return `prepStatementExport_${this.contestId}`
    },
    open () {
      // The official name and day are asked every time, starting from the last export.
      const saved = storage.get(this.storageKey()) || {}
      this.form = {
        title: saved.title || String(this.contestTitle || '').replace(/\s*筹备\s*$/, ''),
        subtitle: typeof saved.subtitle === 'string' ? saved.subtitle : this.$t('m.Prep_Export_Subtitle_Default'),
        date: saved.date || '',
        cover: COVERS.some(option => option.key === saved.cover) ? saved.cover : 'plain'
      }
      this.error = ''
      this.schedulePreview(0)
    },
    close () {
      clearTimeout(this.timer)
      this.rerun = false
      this.preview = { key: '', blob: null, filename: '', problems: '' }
    },
    payload (previewing) {
      return {
        contest_id: Number(this.contestId),
        title: this.form.title.trim(),
        subtitle: this.form.subtitle.trim(),
        date: this.form.date,
        cover: this.form.cover,
        preview: previewing
      }
    },
    schedulePreview (delay = PREVIEW_DELAY_MS) {
      clearTimeout(this.timer)
      if (!this.ready || this.preview.key === this.requestKey) return
      this.timer = setTimeout(this.runPreview, delay)
    },
    async runPreview () {
      if (!this.ready || !this.visible) return
      // The server typesets one export per contest at a time; ask again once this one returns.
      if (this.loading) {
        this.rerun = true
        return
      }
      const key = this.requestKey
      this.loading = true
      try {
        const res = await api.exportPrepStatements(this.payload(true))
        if (!this.visible) return
        if (!String(res.headers['content-type'] || '').includes('pdf')) {
          this.error = await readError(res, this.$t('m.Prep_Export_Failed'))
          return
        }
        const encoded = /filename\*=UTF-8''([^;]+)/i.exec(res.headers['content-disposition'] || '')
        this.preview = {
          key,
          blob: res.data,
          filename: encoded ? decodeURIComponent(encoded[1]) : `${this.form.title.trim()}.pdf`,
          problems: problemsWithWarnings(res)
        }
        this.error = ''
      } catch (_) {
        this.error = this.$t('m.Prep_Export_Failed')
      } finally {
        this.loading = false
        if (this.visible && (this.rerun || this.requestKey !== key)) {
          this.rerun = false
          this.schedulePreview(0)
        }
      }
    },
    renderFailed () {
      this.error = this.$t('m.Prep_Export_Failed')
    },
    async exportStatements () {
      this.exporting = true
      try {
        let blob = null
        let filename = ''
        let problems = ''
        if (this.preview.key === this.requestKey && this.preview.blob) {
          ({ blob, filename, problems } = this.preview)
        } else {
          const res = await api.exportPrepStatements(this.payload(false))
          if (!String(res.headers['content-type'] || '').includes('pdf')) {
            this.$error(await readError(res, this.$t('m.Prep_Export_Failed')))
            return
          }
          const encoded = /filename\*=UTF-8''([^;]+)/i.exec(res.headers['content-disposition'] || '')
          blob = res.data
          filename = encoded ? decodeURIComponent(encoded[1]) : `${this.form.title.trim()}.pdf`
          problems = problemsWithWarnings(res)
        }
        this.saveFile(blob, filename)
        const { title, subtitle, date, cover } = this.payload(false)
        storage.set(this.storageKey(), { title, subtitle, date, cover })
        this.$emit('update:visible', false)
        if (problems) {
          // TeX recovered, but these problems deserve a look in the PDF.
          this.$Message.warning({ message: this.$t('m.Prep_Export_Warnings', { problems }), duration: 8000 })
        } else {
          this.$success(this.$t('m.Prep_Export_Done'))
        }
      } catch (_) {
        this.$error(this.$t('m.Prep_Export_Failed'))
      } finally {
        this.exporting = false
      }
    },
    saveFile (blob, filename) {
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      try {
        link.href = url
        link.download = filename
        document.body.appendChild(link)
        link.click()
      } finally {
        link.remove()
        window.setTimeout(() => window.URL.revokeObjectURL(url), 1000)
      }
    }
  }
}
</script>

<style scoped lang="less">
.export-layout {
  display: grid;
  grid-template-columns: minmax(0, 360px) minmax(0, 1fr);
  gap: 22px;
}
.export-note { margin: 0 0 14px; color: var(--color-text-muted); font-size: 13px; line-height: 1.6; }
.export-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 12px; }
.cover-options { display: grid; width: 100%; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.cover-option {
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 6px 4px 7px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
  color: var(--color-text-muted);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: border-color .2s ease, box-shadow .2s ease, color .2s ease;
  &:hover, &:focus-visible { border-color: var(--line-strong); color: var(--color-text); outline: none; }
  &.is-active { border-color: var(--color-link); box-shadow: 0 0 0 1px var(--color-link); color: var(--color-text); }
}
.cover-thumb {
  display: flex;
  width: 100%;
  height: 72px;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  background: var(--color-bg-subtle);
  img { max-width: 100%; max-height: 100%; object-fit: contain; }
  :deep(.legacy-icon) { display: inline-flex; color: var(--color-text-faint); }
  :deep(svg) { width: 26px; height: 26px; }
}
.cover-label { overflow: hidden; max-width: 100%; text-overflow: ellipsis; white-space: nowrap; }
.export-warning { margin: 4px 0 0; color: var(--cat-course); font-size: 12px; line-height: 1.6; }
// Stretched to the form's height by the grid; the pages scroll inside instead of growing it.
.export-preview {
  position: relative;
  overflow: hidden;
  min-height: 420px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg-subtle);
  > .pdf-pages { position: absolute; inset: 0; }
}
.preview-state {
  position: absolute;
  inset: 0;
  background: var(--color-bg-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: var(--color-text-muted);
  font-size: 13px;
  text-align: center;
  &.is-over { inset: auto 14px 14px auto; padding: 6px 12px; border-radius: 999px; background: rgba(15, 15, 15, .72); color: #fff; }
  &.is-error { color: var(--oj-danger); }
  :deep(.legacy-icon) { display: inline-flex; }
}
.is-spinning { animation: export-spin .9s linear infinite; }
@keyframes export-spin { to { transform: rotate(360deg); } }

@media (max-width: 820px) {
  .export-layout { grid-template-columns: 1fr; }
  .export-preview { min-height: 0; height: 60vh; }
}
</style>
