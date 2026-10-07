<template>
  <div class="markdown-editor-adapter">
    <div class="markdown-editor-toolbar">
      <div class="markdown-format-actions" aria-label="Markdown 格式工具">
        <button type="button" title="加粗" aria-label="加粗" @mousedown.prevent @click="applyFormat('bold')"><strong>B</strong></button>
        <button type="button" title="倾斜" aria-label="倾斜" @mousedown.prevent @click="applyFormat('italic')"><em>I</em></button>
        <button type="button" title="下划线" aria-label="下划线" @mousedown.prevent @click="applyFormat('underline')"><u>U</u></button>
        <button type="button" title="删除线" aria-label="删除线" @mousedown.prevent @click="applyFormat('strikethrough')"><s>S</s></button>
        <button type="button" title="行内代码" aria-label="行内代码" @mousedown.prevent @click="applyFormat('code')"><span>&lt;/&gt;</span></button>
        <button type="button" title="行内公式" aria-label="行内公式" @mousedown.prevent @click="applyFormat('formula')"><span>∑</span></button>
      </div>
      <div class="markdown-mode-switch" role="group" aria-label="编辑模式">
        <button type="button" :class="{ active: mode === 'raw' }" @click="setMode('raw')">原文</button>
        <button type="button" :class="{ active: mode === 'preview' }" @click="setMode('preview')">预览</button>
      </div>
    </div>
    <textarea v-show="mode === 'raw'"
              ref="rawEditor"
              v-model="source"
              class="markdown-raw-editor"
              spellcheck="false"
              @input="emitMarkdown"></textarea>
    <div v-show="mode === 'preview'"
         ref="previewEditor"
         class="markdown-preview markdown-body"
         contenteditable="true"
         role="textbox"
         aria-multiline="true"
         spellcheck="true"
         v-html="previewHtml"
         @input="onPreviewInput"
         @blur="syncPreviewHtml"
         v-katex
         v-highlight></div>
  </div>
</template>

<script>
import markdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import TurndownService from 'turndown'
import { gfm } from 'turndown-plugin-gfm'

const renderer = markdownIt({
  html: true,
  breaks: true,
  linkify: true
})

function createTurndown () {
  const service = new TurndownService({
    bulletListMarker: '-',
    codeBlockStyle: 'fenced',
    emDelimiter: '*',
    strongDelimiter: '**'
  })
  service.use(gfm)
  service.keep(['u'])
  return service
}

function htmlToMarkdown (value, turndown) {
  let content = String(value || '')
  if (!/<[a-z][\s\S]*>/i.test(content)) return content
  content = DOMPurify.sanitize(content)
  if (typeof document !== 'undefined' && content.includes('katex')) {
    const root = document.createElement('div')
    root.innerHTML = content
    root.querySelectorAll('.katex').forEach(node => {
      if (node.parentElement && node.parentElement.closest('.katex')) return
      const annotation = node.querySelector('annotation[encoding="application/x-tex"]')
      if (!annotation) return
      const display = Boolean(node.closest('.katex-display'))
      node.replaceWith(document.createTextNode(display
        ? `$$${annotation.textContent || ''}$$`
        : `$${annotation.textContent || ''}$`))
    })
    content = root.innerHTML
  }
  const math = []
  const protectedHtml = content.replace(
    /\$\$[\s\S]*?\$\$|\$[^$]+\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]/g,
    expression => {
      const token = `MARKDOWNMATHPLACEHOLDER${math.length}X`
      math.push(expression)
      return token
    }
  )
  let markdown = turndown.turndown(protectedHtml)
  math.forEach((expression, index) => {
    markdown = markdown.replace(`MARKDOWNMATHPLACEHOLDER${index}X`, expression)
  })
  return markdown
}

export default {
  name: 'RichTextEditorAdapter',
  props: {
    value: { type: String, default: '' },
    modelValue: { type: String, default: undefined }
  },
  emits: ['input', 'change', 'update:value', 'update:modelValue'],
  data () {
    return {
      mode: 'raw',
      source: '',
      previewHtml: '',
      lastRenderedHtml: '',
      turndown: null
    }
  },
  computed: {
    content () {
      return this.modelValue === undefined ? this.value : this.modelValue
    }
  },
  mounted () {
    this.turndown = createTurndown()
    this.source = htmlToMarkdown(this.content, this.turndown)
    this.previewHtml = DOMPurify.sanitize(renderer.render(this.source))
    this.lastRenderedHtml = this.previewHtml
  },
  watch: {
    content (value) {
      if (!this.turndown || value === this.lastRenderedHtml) return
      this.source = htmlToMarkdown(value, this.turndown)
      this.previewHtml = DOMPurify.sanitize(renderer.render(this.source))
      this.lastRenderedHtml = this.previewHtml
    }
  },
  methods: {
    emitValue (html) {
      html = DOMPurify.sanitize(html)
      this.lastRenderedHtml = html
      this.$emit('input', html)
      this.$emit('change', html)
      this.$emit('update:value', html)
      this.$emit('update:modelValue', html)
    },
    emitMarkdown () {
      const html = DOMPurify.sanitize(renderer.render(this.source || ''))
      this.previewHtml = html
      this.emitValue(html)
    },
    onPreviewInput () {
      const editor = this.$refs.previewEditor
      if (!editor || !this.turndown) return
      const html = editor.innerHTML
      this.source = htmlToMarkdown(html, this.turndown)
      this.emitValue(html)
    },
    syncPreviewHtml () {
      const editor = this.$refs.previewEditor
      if (editor) this.previewHtml = DOMPurify.sanitize(editor.innerHTML)
    },
    setMode (mode) {
      if (this.mode === 'preview') this.syncPreviewHtml()
      this.mode = mode
      if (mode === 'preview') this.previewHtml = DOMPurify.sanitize(renderer.render(this.source || ''))
      this.$nextTick(() => {
        if (mode === 'raw') this.$refs.rawEditor?.focus()
        else this.$refs.previewEditor?.focus()
      })
    },
    applyFormat (type) {
      const rawFormats = {
        bold: ['**', '**', 'bold'],
        italic: ['*', '*', 'italic'],
        underline: ['<u>', '</u>', 'underline'],
        strikethrough: ['~~', '~~', 'strikethrough'],
        code: ['`', '`', 'code']
      }
      if (this.mode === 'raw') {
        if (type === 'formula') {
          this.wrapSelection('$', '$', 'a+b')
          return
        }
        this.wrapSelection(...rawFormats[type])
        return
      }
      const editor = this.$refs.previewEditor
      if (!editor) return
      editor.focus()
      const commands = {
        bold: 'bold',
        italic: 'italic',
        underline: 'underline',
        strikethrough: 'strikeThrough'
      }
      if (commands[type]) {
        document.execCommand(commands[type], false, null)
      } else if (type === 'formula') {
        const selection = window.getSelection()
        const text = selection && selection.toString() ? selection.toString() : 'a+b'
        document.execCommand('insertText', false, `$${text}$`)
      } else if (type === 'code') {
        this.wrapPreviewSelection('code', 'code')
      }
      this.onPreviewInput()
    },
    wrapPreviewSelection (tagName, placeholder) {
      const editor = this.$refs.previewEditor
      const selection = window.getSelection()
      if (!editor || !selection || !selection.rangeCount) return
      const range = selection.getRangeAt(0)
      if (!editor.contains(range.commonAncestorContainer)) return
      const node = document.createElement(tagName)
      if (range.collapsed) node.textContent = placeholder
      else node.appendChild(range.extractContents())
      range.insertNode(node)
      range.selectNodeContents(node)
      selection.removeAllRanges()
      selection.addRange(range)
    },
    wrapSelection (before, after, placeholder) {
      this.$nextTick(() => {
        const editor = this.$refs.rawEditor
        if (!editor) return
        const start = editor.selectionStart
        const end = editor.selectionEnd
        const selection = this.source.slice(start, end) || placeholder
        const replacement = `${before}${selection}${after}`
        this.source = `${this.source.slice(0, start)}${replacement}${this.source.slice(end)}`
        this.emitMarkdown()
        this.$nextTick(() => {
          editor.focus()
          const selectionStart = start + before.length
          editor.setSelectionRange(selectionStart, selectionStart + selection.length)
        })
      })
    }
  }
}
</script>

<style scoped lang="less">
.markdown-editor-adapter { width: 100%; overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg); box-sizing: border-box; }
.markdown-editor-toolbar { display: flex; min-height: 42px; align-items: center; justify-content: space-between; gap: 12px; padding: 5px 7px; border-bottom: 1px solid var(--color-border); background: var(--color-bg); }
.markdown-format-actions, .markdown-mode-switch { display: flex; align-items: center; gap: 2px; }
.markdown-editor-toolbar button { appearance: none; display: inline-grid; min-width: 30px; height: 30px; place-items: center; padding: 0 7px; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--color-text-muted); cursor: pointer; font-family: var(--font-sans); font-size: 13px; transition: color var(--transition), background-color var(--transition); }
.markdown-editor-toolbar button:hover, .markdown-editor-toolbar button:focus-visible { background: var(--color-bg-subtle); color: var(--color-text); outline: none; }
.markdown-mode-switch { padding: 2px; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-bg-subtle); }
.markdown-mode-switch button { display: inline-flex; min-width: 62px; height: 26px; align-items: center; justify-content: center; border-radius: 4px; font-size: 12px; line-height: 1; }
.markdown-mode-switch button.active { background: var(--color-bg); color: var(--color-text); box-shadow: 0 1px 3px rgba(55, 53, 47, .09); }
.markdown-raw-editor { display: block; width: 100%; min-height: 190px; resize: vertical; padding: 13px 15px; border: 0; outline: 0; background: var(--color-bg); color: var(--color-text); box-sizing: border-box; font-family: var(--font-mono); font-size: 13px; line-height: 1.7; tab-size: 2; }
.markdown-preview { min-height: 190px; padding: 13px 15px; color: var(--color-text); cursor: text; outline: 0; }
.markdown-preview:focus { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--color-link) 52%, transparent); }
.markdown-preview :deep(> :last-child) { margin-bottom: 0; }

@media (max-width: 640px) {
  .markdown-editor-toolbar { align-items: flex-start; flex-direction: column; }
  .markdown-mode-switch { align-self: flex-end; }
}
</style>
