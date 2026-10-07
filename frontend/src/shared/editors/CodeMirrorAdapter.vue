<template><div ref="host" class="cm6-adapter"></div></template>
<script>
import { EditorState, Compartment } from '@codemirror/state'
import { bracketMatching, HighlightStyle, indentOnInput, indentUnit, syntaxHighlighting } from '@codemirror/language'
import { EditorView, keymap, lineNumbers } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { autocompletion, closeBrackets, closeBracketsKeymap, completionKeymap, snippetCompletion } from '@codemirror/autocomplete'
import { cpp } from '@codemirror/lang-cpp'
import { java } from '@codemirror/lang-java'
import { python } from '@codemirror/lang-python'
import { javascript } from '@codemirror/lang-javascript'
import { tags } from '@lezer/highlight'

const cppHeaders = [
  'bits/stdc++.h', 'iostream', 'vector', 'string', 'algorithm', 'numeric',
  'map', 'unordered_map', 'set', 'unordered_set', 'queue', 'stack',
  'deque', 'array', 'tuple', 'utility', 'cmath', 'iomanip', 'limits'
]

const cHeaders = ['stdio.h', 'stdlib.h', 'string.h', 'math.h', 'ctype.h', 'limits.h']

const cppCompletions = [
  snippetCompletion('int main() {\n\t${0}\n\treturn 0;\n}', { label: 'main', type: 'function', detail: 'C++ main function', boost: 100 }),
  snippetCompletion('for (int ${i} = 0; ${i} < ${n}; ++${i}) {\n\t${0}\n}', { label: 'for', type: 'keyword', detail: 'indexed loop', boost: 90 }),
  snippetCompletion('for (const auto& ${item} : ${container}) {\n\t${0}\n}', { label: 'foreach', type: 'keyword', detail: 'range-based loop', boost: 85 }),
  snippetCompletion('if (${condition}) {\n\t${0}\n}', { label: 'if', type: 'keyword', detail: 'condition block' }),
  snippetCompletion(`std::cin >> \${value};`, { label: 'cin', type: 'function', detail: 'standard input' }),
  snippetCompletion(`std::cout << \${value} << '\\n';`, { label: 'cout', type: 'function', detail: 'standard output' }),
  snippetCompletion('std::sort(${begin}, ${end});', { label: 'sort', type: 'function', detail: '<algorithm>' }),
  snippetCompletion('std::lower_bound(${begin}, ${end}, ${value})', { label: 'lower_bound', type: 'function', detail: '<algorithm>' }),
  snippetCompletion('std::upper_bound(${begin}, ${end}, ${value})', { label: 'upper_bound', type: 'function', detail: '<algorithm>' }),
  snippetCompletion('std::accumulate(${begin}, ${end}, ${initial})', { label: 'accumulate', type: 'function', detail: '<numeric>' }),
  snippetCompletion('std::getline(${stream}, ${value});', { label: 'getline', type: 'function', detail: '<string>' }),
  snippetCompletion('${container}.push_back(${value});', { label: 'push_back', type: 'method', detail: 'append an element' }),
  snippetCompletion('${container}.emplace_back(${value});', { label: 'emplace_back', type: 'method', detail: 'construct an element' }),
  { label: 'vector', type: 'class', detail: 'std::vector' },
  { label: 'string', type: 'class', detail: 'std::string' },
  { label: 'pair', type: 'class', detail: 'std::pair' },
  { label: 'tuple', type: 'class', detail: 'std::tuple' },
  { label: 'map', type: 'class', detail: 'std::map' },
  { label: 'unordered_map', type: 'class', detail: 'std::unordered_map' },
  { label: 'set', type: 'class', detail: 'std::set' },
  { label: 'queue', type: 'class', detail: 'std::queue' },
  { label: 'stack', type: 'class', detail: 'std::stack' },
  { label: 'priority_queue', type: 'class', detail: 'std::priority_queue' },
  { label: 'min', type: 'function', detail: 'std::min' },
  { label: 'max', type: 'function', detail: 'std::max' },
  { label: 'swap', type: 'function', detail: 'std::swap' },
  { label: 'using namespace std;', type: 'keyword', apply: 'using namespace std;' }
]

const cCompletions = [
  snippetCompletion('int main(void) {\n\t${0}\n\treturn 0;\n}', { label: 'main', type: 'function', detail: 'C main function', boost: 100 }),
  snippetCompletion('for (int ${i} = 0; ${i} < ${n}; ++${i}) {\n\t${0}\n}', { label: 'for', type: 'keyword', detail: 'indexed loop' }),
  snippetCompletion('printf("${format}\\n", ${value});', { label: 'printf', type: 'function', detail: '<stdio.h>' }),
  snippetCompletion('scanf("${format}", &${value});', { label: 'scanf', type: 'function', detail: '<stdio.h>' }),
  { label: 'malloc', type: 'function', detail: '<stdlib.h>' },
  { label: 'free', type: 'function', detail: '<stdlib.h>' },
  { label: 'strlen', type: 'function', detail: '<string.h>' },
  { label: 'memset', type: 'function', detail: '<string.h>' },
  { label: 'memcpy', type: 'function', detail: '<string.h>' },
  { label: 'qsort', type: 'function', detail: '<stdlib.h>' }
]

const headerCompletionSource = headers => context => {
  const line = context.state.doc.lineAt(context.pos)
  const before = context.state.sliceDoc(line.from, context.pos)
  const headerMatch = before.match(/#\s*include\s*([<"]?)([\w./-]*)$/)
  if (headerMatch) {
    const opener = headerMatch[1]
    const typed = headerMatch[2]
    const closer = opener === '"' ? '"' : '>'
    return {
      from: context.pos - typed.length,
      options: headers.map(header => ({
        label: `<${header}>`,
        type: 'text',
        apply: `${opener ? '' : '<'}${header}${closer}`
      })),
      validFor: /^[\w./-]*$/
    }
  }

  const directiveMatch = before.match(/#\w*$/)
  if (directiveMatch) {
    return {
      from: context.pos - directiveMatch[0].length,
      options: [snippetCompletion('#include <${header}>', { label: '#include', type: 'keyword', boost: 120 })],
      validFor: /^#\w*$/
    }
  }
  return null
}

const completionSource = (headers, completions) => {
  const completeHeader = headerCompletionSource(headers)
  return context => {
    const header = completeHeader(context)
    if (header) return header
    const word = context.matchBefore(/\w*/)
    if (!word || (word.from === word.to && !context.explicit)) return null
    return { from: word.from, options: completions, validFor: /^\w*$/ }
  }
}

const cppCompletionSource = completionSource(cppHeaders, cppCompletions)
const cCompletionSource = completionSource(cHeaders, cCompletions)

const languageFor = (mode = '') => {
  const value = mode.toLowerCase()
  if (value.includes('python')) return python()
  if (value.includes('java') && !value.includes('javascript')) return java()
  if (value.includes('javascript') || value.includes('node')) return javascript()
  return cpp()
}

const completionFor = (mode = '') => {
  const value = mode.toLowerCase()
  const source = value.includes('c++') || value.includes('cpp')
    ? cppCompletionSource
    : (value.includes('csrc') ? cCompletionSource : null)
  return autocompletion({
    activateOnTyping: true,
    closeOnBlur: true,
    maxRenderedOptions: 12,
    ...(source ? { override: [source] } : {})
  })
}

const syntaxFor = () => {
  // The three legacy theme choices are retained for compatibility, but the
  // Feiyue editor stays transparent and uses one stable syntax palette so a
  // theme selection never unexpectedly recolors the code surface.
  const colors = {
    keyword: '#9a3d3d', atom: '#9a6b1f', string: '#26756d', comment: '#8b8983',
    variable: '#2f6f9f', type: '#73528f', number: '#9a4f83', operator: '#5f625e'
  }
  return syntaxHighlighting(HighlightStyle.define([
    { tag: tags.keyword, color: colors.keyword },
    { tag: [tags.atom, tags.bool, tags.null], color: colors.atom },
    { tag: tags.string, color: colors.string },
    { tag: tags.comment, color: colors.comment, fontStyle: 'italic' },
    { tag: [tags.variableName, tags.propertyName], color: colors.variable },
    { tag: [tags.typeName, tags.className], color: colors.type },
    { tag: tags.number, color: colors.number },
    { tag: tags.operator, color: colors.operator }
  ]))
}

const editorThemeFor = (theme) => {
  const themes = {
    solarized: {
      background: 'transparent', foreground: '#37352f', gutter: 'transparent', gutterText: '#787774', gutterBorder: 'var(--color-border)', selection: 'rgba(35, 131, 226, .16)', activeLine: 'rgba(247, 246, 243, .72)'
    }
  }
  const palette = themes[theme] || themes.solarized
  return EditorView.theme({
    '&': { color: palette.foreground, backgroundColor: palette.background },
    '.cm-content': { caretColor: palette.foreground },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: palette.foreground },
    '.cm-gutters': { backgroundColor: palette.gutter, color: palette.gutterText, border: 'none', borderRight: `1px solid ${palette.gutterBorder}` },
    '.cm-activeLine': { backgroundColor: palette.activeLine },
    '.cm-activeLineGutter': { backgroundColor: palette.gutter },
    '.cm-selectionBackground, ::selection': { backgroundColor: palette.selection },
    '&.cm-focused .cm-selectionBackground, &.cm-focused ::selection': { backgroundColor: palette.selection }
  }, { dark: false })
}

export default {
  name: 'CodeMirrorAdapter',
  props: {
    value: { type: String, default: '' },
    modelValue: { type: String, default: undefined },
    mode: { type: String, default: 'text/x-csrc' },
    theme: { type: String, default: 'solarized' },
    readOnly: { type: Boolean, default: false },
    lineWrapping: { type: Boolean, default: true },
    autofocus: { type: Boolean, default: false }
  },
  emits: ['input', 'change', 'update:value', 'update:modelValue'],
  data: () => ({ view: null, languageSlot: new Compartment(), completionSlot: new Compartment(), editableSlot: new Compartment(), themeSlot: new Compartment() }),
  computed: { content () { return this.modelValue === undefined ? this.value : this.modelValue } },
  mounted () {
    this.view = new EditorView({
      parent: this.$refs.host,
      state: EditorState.create({
        doc: this.content || '',
        extensions: [
          lineNumbers(), history(),
          bracketMatching(), closeBrackets(), indentOnInput(), indentUnit.of('    '), EditorState.tabSize.of(4),
          keymap.of([...closeBracketsKeymap, ...completionKeymap, ...historyKeymap, ...defaultKeymap, indentWithTab]),
          this.languageSlot.of(languageFor(this.mode)),
          this.completionSlot.of(completionFor(this.mode)),
          this.editableSlot.of(EditorView.editable.of(!this.readOnly)),
          this.themeSlot.of([editorThemeFor(this.theme), syntaxFor()]),
          this.lineWrapping ? EditorView.lineWrapping : [],
          EditorView.updateListener.of(update => {
            if (!update.docChanged) return
            const value = update.state.doc.toString()
            this.$emit('input', value)
            this.$emit('change', value)
            this.$emit('update:value', value)
            this.$emit('update:modelValue', value)
          })
        ]
      })
    })
    if (this.autofocus) this.view.focus()
  },
  beforeUnmount () { if (this.view) this.view.destroy() },
  watch: {
    content (value) {
      if (!this.view || value === this.view.state.doc.toString()) return
      this.view.dispatch({ changes: { from: 0, to: this.view.state.doc.length, insert: value || '' } })
    },
    mode (value) {
      this.reconfigure([
        this.languageSlot.reconfigure(languageFor(value)),
        this.completionSlot.reconfigure(completionFor(value))
      ])
    },
    theme (value) { this.reconfigure(this.themeSlot.reconfigure([editorThemeFor(value), syntaxFor()])) },
    readOnly (value) { this.reconfigure(this.editableSlot.reconfigure(EditorView.editable.of(!value))) }
  },
  methods: {
    reconfigure (effect) { if (this.view) this.view.dispatch({ effects: effect }) },
    focus () { if (this.view) this.view.focus() },
    setValue (value) {
      if (this.view) this.view.dispatch({ changes: { from: 0, to: this.view.state.doc.length, insert: value || '' } })
    },
    setOption (name, value) {
      if (name === 'mode') {
        this.reconfigure([
          this.languageSlot.reconfigure(languageFor(value)),
          this.completionSlot.reconfigure(completionFor(value))
        ])
      }
      if (name === 'readOnly') this.reconfigure(this.editableSlot.reconfigure(EditorView.editable.of(!value)))
    }
  }
}
</script>
<style>
.cm6-adapter .cm-editor { min-height: 300px; max-height: 1000px; overflow: auto; border: 1px solid var(--el-border-color); background: transparent !important; }
.cm6-adapter .cm-editor:focus,
.cm6-adapter .cm-editor.cm-focused { outline: none !important; box-shadow: none !important; }
.cm6-adapter .cm-gutters { background: transparent !important; }
.cm6-adapter .cm-scroller { font-family: 'JetBrainsMono Nerd Font', 'JetBrains Mono', 'Fira Code Nerd Font', 'Fira Code', 'Cascadia Code', 'SF Mono', Menlo, Consolas, monospace; font-variant-ligatures: none; }
.cm6-adapter .cm-tooltip-autocomplete { overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg); box-shadow: 0 8px 20px rgba(55, 53, 47, .07); animation: cm-completion-in 150ms ease both; }
.cm6-adapter .cm-tooltip-autocomplete > ul { min-width: 280px; max-width: min(420px, 80vw); max-height: 232px; padding: 4px; background: var(--color-bg); font-family: var(--font-sans); scrollbar-color: var(--color-border) var(--color-bg); scrollbar-width: thin; }
.cm6-adapter .cm-tooltip-autocomplete > ul::-webkit-scrollbar { width: 8px; }
.cm6-adapter .cm-tooltip-autocomplete > ul::-webkit-scrollbar-track { background: var(--color-bg); }
.cm6-adapter .cm-tooltip-autocomplete > ul::-webkit-scrollbar-thumb { border: 2px solid var(--color-bg); border-radius: var(--radius-pill); background: var(--color-border); }
.cm6-adapter .cm-tooltip-autocomplete > ul::-webkit-scrollbar-thumb:hover { background: var(--line-strong); }
.cm6-adapter .cm-tooltip-autocomplete > ul > li { display: flex; min-height: 30px; align-items: center; gap: 10px; padding: 5px 9px; border-radius: 0; background: transparent; color: var(--color-text-muted); line-height: 18px; }
.cm6-adapter .cm-tooltip-autocomplete > ul > li[aria-selected] { background: var(--color-bg-subtle); color: var(--color-text); }
.cm6-adapter .cm-completionIcon { display: none; }
.cm6-adapter .cm-completionLabel { min-width: 0; flex: 1; overflow: hidden; font-family: 'JetBrainsMono Nerd Font', 'JetBrains Mono', 'Fira Code Nerd Font', monospace; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.cm6-adapter .cm-completionDetail { flex: none; margin-left: auto; color: var(--color-text-faint); font-size: 11px; font-style: normal; white-space: nowrap; }
.cm6-adapter .cm-completionMatchedText { color: var(--color-link); font-weight: 650; text-decoration: none; }
@keyframes cm-completion-in { from { opacity: 0; transform: translateY(-2px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .cm6-adapter .cm-tooltip-autocomplete { animation: none; } }
</style>
