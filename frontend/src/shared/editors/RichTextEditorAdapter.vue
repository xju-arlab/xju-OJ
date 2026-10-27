<template>
  <div :class="['markdown-editor-adapter', { 'is-compact': compact }]">
    <div class="markdown-editor-toolbar">
      <div class="markdown-format-actions" aria-label="Markdown 格式工具">
        <button type="button" title="加粗" aria-label="加粗" @mousedown.prevent @click="applyFormat('bold')"><strong>B</strong></button>
        <button type="button" title="倾斜" aria-label="倾斜" @mousedown.prevent @click="applyFormat('italic')"><em>I</em></button>
        <button type="button" title="下划线" aria-label="下划线" @mousedown.prevent @click="applyFormat('underline')"><u>U</u></button>
        <button type="button" title="删除线" aria-label="删除线" @mousedown.prevent @click="applyFormat('strikethrough')"><s>S</s></button>
        <button type="button" title="行内代码" aria-label="行内代码" @mousedown.prevent @click="applyFormat('code')"><span>&lt;/&gt;</span></button>
        <button type="button" title="行内公式" aria-label="行内公式" @mousedown.prevent @click="applyFormat('formula')"><span>∑</span></button>
        <template v-if="imageUpload">
          <span class="markdown-toolbar-divider" aria-hidden="true"></span>
          <button type="button" class="markdown-image-button" :disabled="uploadingImages > 0"
                  :title="uploadingImages ? '图片上传中…' : '插入图片（也可直接粘贴截图）'" aria-label="插入图片"
                  @mousedown.prevent @click="pickImage">
            <Icon :type="uploadingImages ? 'loading' : 'image'" :class="{ 'is-spinning': uploadingImages }" />
          </button>
          <input ref="imageInput" type="file" accept="image/png,image/jpeg,image/gif,image/webp,image/bmp"
                 multiple hidden @change="onImagePicked">
        </template>
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
              :placeholder="placeholder"
              spellcheck="false"
              @input="emitMarkdown"
              @paste="onPaste"></textarea>
    <div v-show="mode === 'preview'"
         ref="previewEditor"
         class="markdown-preview markdown-body"
         contenteditable="true"
         role="textbox"
         aria-multiline="true"
         spellcheck="true"
         v-html="previewHtml"
         @input="onPreviewInput"
         @paste="onPaste"
         @blur="syncPreviewHtml"
         v-katex
         v-highlight></div>
  </div>
</template>

<script>
import DOMPurify from 'dompurify'
import { createTurndown, htmlToMarkdown, renderMarkdown } from './richTextMarkdown'
import { csrfHeaders } from '@/utils/csrf'
import { compressImageToWebP } from '@/utils/imageCompress'

export default {
  name: 'RichTextEditorAdapter',
  props: {
    value: { type: String, default: '' },
    modelValue: { type: String, default: undefined },
    // { action, data }: where statement images go. Without it there is no image button.
    imageUpload: { type: Object, default: null },
    // A shorter box for secondary text such as sample explanations.
    compact: { type: Boolean, default: false },
    placeholder: { type: String, default: '' }
  },
  emits: ['input', 'change', 'update:value', 'update:modelValue'],
  data () {
    return {
      mode: 'raw',
      source: '',
      previewHtml: '',
      lastRenderedHtml: '',
      turndown: null,
      uploadingImages: 0
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
    this.previewHtml = DOMPurify.sanitize(renderMarkdown(this.source))
    this.lastRenderedHtml = this.previewHtml
  },
  watch: {
    content (value) {
      if (!this.turndown || value === this.lastRenderedHtml) return
      this.source = htmlToMarkdown(value, this.turndown)
      this.previewHtml = DOMPurify.sanitize(renderMarkdown(this.source))
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
      const html = DOMPurify.sanitize(renderMarkdown(this.source || ''))
      this.previewHtml = html
      this.emitValue(html)
    },
    onPreviewInput () {
      const editor = this.$refs.previewEditor
      if (!editor || !this.turndown) return
      this.source = htmlToMarkdown(editor.innerHTML, this.turndown)
      // Emit the Markdown rendering, never the live preview DOM: KaTeX markup
      // must not reach the server, and the stored HTML keeps the $...$ source.
      this.emitValue(renderMarkdown(this.source))
    },
    syncPreviewHtml () {
      const editor = this.$refs.previewEditor
      if (editor) this.previewHtml = DOMPurify.sanitize(editor.innerHTML)
    },
    setMode (mode) {
      if (this.mode === 'preview') this.syncPreviewHtml()
      this.mode = mode
      if (mode === 'preview') this.previewHtml = DOMPurify.sanitize(renderMarkdown(this.source || ''))
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
    pickImage () {
      this.savedRange = this.mode === 'preview' ? this.previewRange() : null
      const input = this.$refs.imageInput
      if (!input) return
      input.value = ''
      input.click()
    },
    previewRange () {
      const editor = this.$refs.previewEditor
      const selection = window.getSelection()
      if (!editor || !selection || !selection.rangeCount) return null
      const range = selection.getRangeAt(0)
      return editor.contains(range.commonAncestorContainer) ? range.cloneRange() : null
    },
    onImagePicked (event) {
      this.uploadImages(Array.from(event.target.files || []))
    },
    onPaste (event) {
      if (!this.imageUpload) return
      const files = Array.from((event.clipboardData && event.clipboardData.files) || [])
        .filter(file => file.type.startsWith('image/'))
      if (!files.length) return
      event.preventDefault()
      if (this.mode === 'preview') this.savedRange = this.previewRange()
      this.uploadImages(files)
    },
    async uploadImages (files) {
      const images = files.filter(file => file.type.startsWith('image/'))
      if (!images.length) return
      this.uploadingImages += 1
      try {
        for (const original of images) {
          const file = await compressImageToWebP(original)
          this.insertImage(await this.uploadImage(file), original.name)
        }
      } catch (error) {
        if (this.$error) this.$error(error.message || '图片上传失败')
      } finally {
        this.uploadingImages -= 1
      }
    },
    async uploadImage (file) {
      const form = new FormData()
      Object.entries(this.imageUpload.data || {}).forEach(([key, value]) => form.append(key, value))
      form.append('image', file, file.name)
      const response = await fetch(this.imageUpload.action, {
        method: 'POST',
        body: form,
        credentials: 'same-origin',
        headers: csrfHeaders()
      })
      let body = {}
      try {
        body = await response.json()
      } catch (_) {
        // Not JSON: reported below.
      }
      // The admin upload answers {success, file_path, msg}; the prep upload {error, data}.
      const path = body.file_path || (body.data && body.data.file_path)
      if (!response.ok || !path) {
        throw new Error(body.msg || (typeof body.data === 'string' ? body.data : '') || '图片上传失败')
      }
      return path
    },
    insertImage (path, name) {
      const alt = String(name || '').replace(/\.[^.]*$/, '').replace(/[[\]()]/g, '').trim() || 'image'
      if (this.mode === 'raw') {
        const editor = this.$refs.rawEditor
        const start = editor ? editor.selectionStart : this.source.length
        const end = editor ? editor.selectionEnd : start
        const before = this.source.slice(0, start)
        const after = this.source.slice(end)
        // Its own paragraph, so the statement can lay the picture out as a figure.
        const lead = !before || before.endsWith('\n\n') ? '' : before.endsWith('\n') ? '\n' : '\n\n'
        const trail = !after ? '\n' : after.startsWith('\n\n') ? '' : after.startsWith('\n') ? '\n' : '\n\n'
        const snippet = `${lead}![${alt}](${path})${trail}`
        this.source = before + snippet + after
        this.emitMarkdown()
        this.$nextTick(() => {
          if (!editor) return
          const caret = before.length + snippet.length
          editor.focus()
          editor.setSelectionRange(caret, caret)
        })
        return
      }
      const editor = this.$refs.previewEditor
      const selection = window.getSelection()
      if (!editor || !selection) return
      editor.focus()
      let range = this.savedRange
      if (!range) {
        range = document.createRange()
        range.selectNodeContents(editor)
        range.collapse(false)
      }
      selection.removeAllRanges()
      selection.addRange(range)
      document.execCommand('insertImage', false, path)
      this.savedRange = this.previewRange()
      this.onPreviewInput()
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
.markdown-toolbar-divider { width: 1px; height: 18px; margin: 0 4px; background: var(--color-border); }
.markdown-image-button :deep(.legacy-icon) { display: inline-flex; }
.markdown-image-button :deep(svg) { width: 16px; height: 16px; }
.markdown-image-button:disabled { cursor: wait; opacity: .7; }
.markdown-image-button .is-spinning { animation: markdown-image-spin .9s linear infinite; }
@keyframes markdown-image-spin { to { transform: rotate(360deg); } }
.markdown-preview :deep(img) { max-width: 100%; height: auto; }
.markdown-raw-editor::placeholder { color: var(--color-text-faint); font-family: var(--font-sans); }
.is-compact .markdown-raw-editor, .is-compact .markdown-preview { min-height: 92px; }
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
