<template>
  <div ref="scroller" class="pdf-pages">
    <div v-for="page in pages" :key="page.index" :ref="el => bindPage(page.index, el)" class="pdf-page"
         :style="{ aspectRatio: page.ratio }" :data-index="page.index"></div>
  </div>
</template>

<script>
// pdf.js and its worker load only when the first PDF is shown. The worker is bundled through
// Vite's ?worker import so it ships as .js: nginx serves .mjs as application/octet-stream,
// which browsers refuse for module scripts.
let pdfjsLoader = null
function loadPdfjs () {
  if (!pdfjsLoader) {
    pdfjsLoader = Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?worker')])
      .then(([pdfjs, { default: PdfWorker }]) => {
        pdfjs.GlobalWorkerOptions.workerPort = new PdfWorker()
        return pdfjs
      })
      .catch(error => {
        pdfjsLoader = null
        throw error
      })
  }
  return pdfjsLoader
}

// Matches the horizontal padding of .pdf-pages below.
const PAGE_PADDING = 16
const MAX_PAGE_WIDTH = 760
const MAX_PIXEL_RATIO = 2

// Shows a PDF as a plain column of pages: no toolbar, zoom or print, only scrolling.
// A new document repaints page by page over the old one, visible pages first, so the view
// never blanks and keeps its scroll position. Pages are kept as compressed images, not canvases.
export default {
  name: 'PdfPages',
  props: {
    source: { type: Blob, default: null }
  },
  emits: ['loaded', 'error'],
  data () {
    return {
      pages: []
    }
  },
  watch: {
    source (blob) {
      this.load(blob)
    }
  },
  created () {
    // pdf.js objects rely on private fields, which Vue's reactive proxies break; keep them off data.
    // pdf.js 6 tears a document down through its loading task; the document proxy has no destroy().
    this.task = null
    this.sheets = []
    this.slots = new Map()
    this.drawn = new Map()
    this.visible = new Set()
    this.generation = 0
    this.width = 0
    this.stamp = ''
    this.busy = false
    this.canvas = null
  },
  mounted () {
    this.observer = new IntersectionObserver(this.onIntersect, { root: this.$refs.scroller, rootMargin: '100% 0px' })
    this.resizer = new ResizeObserver(this.onResize)
    this.resizer.observe(this.$refs.scroller)
    this.load(this.source)
  },
  beforeUnmount () {
    this.generation += 1
    this.stamp = ''
    this.observer.disconnect()
    this.resizer.disconnect()
    this.drawn.forEach(({ url }) => URL.revokeObjectURL(url))
    this.drawn.clear()
    if (this.task) this.task.destroy()
  },
  methods: {
    async load (blob) {
      const generation = ++this.generation
      if (!blob) {
        this.reset()
        return
      }
      let task = null
      try {
        const pdfjs = await loadPdfjs()
        const data = new Uint8Array(await blob.arrayBuffer())
        if (generation !== this.generation) return
        // The CID fonts XeLaTeX embeds for Chinese need the Adobe CMaps (shipped by vite.config.mjs).
        task = pdfjs.getDocument({ data, cMapUrl: `/static/pdfjs-${pdfjs.version}/cmaps/`, cMapPacked: true })
        const doc = await task.promise
        const sheets = []
        for (let number = 1; number <= doc.numPages; number++) sheets.push(await doc.getPage(number))
        if (generation !== this.generation) {
          task.destroy()
          return
        }
        // Invalidate in-flight paints first: destroying the old document rejects its renders.
        this.stamp = ''
        const previous = this.task
        this.task = task
        this.sheets = sheets
        // Keyed by index, so page boxes are reused and keep showing the old page until repainted.
        this.pages = sheets.map((sheet, index) => {
          const { width, height } = sheet.getViewport({ scale: 1 })
          return { index, ratio: `${width} / ${height}` }
        })
        if (previous) previous.destroy()
        await this.$nextTick()
        if (generation !== this.generation) return
        this.width = this.measure()
        this.stamp = `${generation}:${this.width}`
        this.$emit('loaded', sheets.length)
        this.schedule()
      } catch (error) {
        if (task && task !== this.task) task.destroy()
        if (generation === this.generation) this.$emit('error', error)
      }
    },
    reset () {
      this.stamp = ''
      this.pages = []
      this.sheets = []
      if (this.task) this.task.destroy()
      this.task = null
    },
    measure () {
      const css = Math.min(MAX_PAGE_WIDTH, Math.max(240, this.$refs.scroller.clientWidth - PAGE_PADDING * 2))
      return Math.round(css * Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO))
    },
    bindPage (index, el) {
      const current = this.slots.get(index)
      if (current === el) return
      if (current) this.observer.unobserve(current)
      if (el) {
        this.slots.set(index, el)
        this.observer.observe(el)
        return
      }
      this.slots.delete(index)
      this.visible.delete(index)
      const drawn = this.drawn.get(index)
      if (drawn) URL.revokeObjectURL(drawn.url)
      this.drawn.delete(index)
    },
    onIntersect (entries) {
      for (const entry of entries) {
        const index = Number(entry.target.dataset.index)
        if (entry.isIntersecting) this.visible.add(index)
        else this.visible.delete(index)
      }
      this.schedule()
    },
    onResize () {
      if (!this.sheets.length || !this.width) return
      const width = this.measure()
      if (Math.abs(width - this.width) / this.width < 0.08) return
      this.width = width
      this.stamp = `${this.generation}:${width}`
      this.schedule()
    },
    nextPage () {
      const pending = this.pages.map(page => page.index)
        .filter(index => this.slots.has(index) && (this.drawn.get(index) || {}).stamp !== this.stamp)
      if (!this.stamp || !pending.length) return -1
      const visible = pending.filter(index => this.visible.has(index))
      if (visible.length) return Math.min(...visible)
      const anchor = this.visible.size ? Math.min(...this.visible) : 0
      return pending.reduce((best, index) => (Math.abs(index - anchor) < Math.abs(best - anchor) ? index : best))
    },
    async schedule () {
      // One page at a time; the loop picks up documents or sizes that change while it runs.
      if (this.busy) return
      this.busy = true
      try {
        for (let index = this.nextPage(); index >= 0; index = this.nextPage()) await this.paint(index)
      } finally {
        this.busy = false
      }
    },
    async paint (index) {
      const stamp = this.stamp
      const sheet = this.sheets[index]
      const box = this.slots.get(index)
      const viewport = sheet.getViewport({ scale: this.width / sheet.getViewport({ scale: 1 }).width })
      if (!this.canvas) this.canvas = document.createElement('canvas')
      const canvas = this.canvas
      canvas.width = Math.floor(viewport.width)
      canvas.height = Math.floor(viewport.height)
      let blob = null
      try {
        await sheet.render({ canvas, viewport }).promise
        if (stamp !== this.stamp) return
        blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/webp', 0.92))
      } catch (error) {
        if (stamp !== this.stamp) return
        this.$emit('error', error)
      }
      if (stamp !== this.stamp || this.slots.get(index) !== box) return
      if (!blob) {
        // Mark it done so a page that cannot render does not loop forever.
        this.drawn.set(index, { stamp, url: '' })
        return
      }
      const url = URL.createObjectURL(blob)
      const image = new Image()
      image.alt = ''
      image.src = url
      // Swap only once decoded, so the old page never flashes blank.
      await image.decode().catch(() => {})
      if (stamp !== this.stamp || this.slots.get(index) !== box) {
        URL.revokeObjectURL(url)
        return
      }
      box.replaceChildren(image)
      const drawn = this.drawn.get(index)
      if (drawn && drawn.url) URL.revokeObjectURL(drawn.url)
      this.drawn.set(index, { stamp, url })
    }
  }
}
</script>

<style scoped lang="less">
.pdf-pages {
  display: flex;
  height: 100%;
  box-sizing: border-box;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 16px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: var(--line-strong) transparent;
}
.pdf-page {
  width: 100%;
  max-width: 760px;
  flex: none;
  overflow: hidden;
  border-radius: 2px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(15, 15, 15, .08), 0 6px 18px rgba(15, 15, 15, .07);
  :deep(img) { display: block; width: 100%; height: 100%; }
}
</style>
