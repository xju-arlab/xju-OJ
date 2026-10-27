// Markdown ⇄ HTML both directions for the shared rich-text editor.
//
// The statement is persisted as HTML, while formulas stay in the Markdown as
// KaTeX delimiters ($...$, $$...$$, \(...\), \[...\] — see plugins/katex.js).
// Both conversions therefore have to carry formulas through untouched:
//
//   - rendering Markdown: shield every formula from Markdown syntax, so `\(`,
//     `\[` and the `*` / `_` pairs inside TeX are not consumed as escapes or
//     emphasis;
//   - reading HTML: recover the TeX source *before* sanitizing (DOMPurify
//     drops the MathML <annotation> that holds it) and take formula text from
//     the DOM, so HTML entities such as &lt; come back as the typed character.
//
// Restoring placeholders always goes through a replacer function: a display
// formula contains `$$`, and String.replace would collapse it to `$`.
import markdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import TurndownService from 'turndown'
import { gfm } from 'turndown-plugin-gfm'

const renderer = markdownIt({
  html: true,
  breaks: true,
  linkify: true
})

const MATH_PATTERN = /\$\$[\s\S]*?\$\$|\$[^$]+\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]/g
const PLACEHOLDER = 'MARKDOWNMATHPLACEHOLDER'

const htmlEscapes = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }

function escapeHtml (value) {
  return String(value).replace(/[&<>"']/g, character => htmlEscapes[character])
}

function mathPattern () {
  // A fresh lastIndex per walk keeps replace() from skipping matches.
  return new RegExp(MATH_PATTERN)
}

export function createTurndown () {
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

// Render Markdown, restoring the shielded formulas as escaped text.
export function renderMarkdown (source) {
  const math = []
  const guarded = String(source || '').replace(mathPattern(), expression => {
    math.push(expression)
    return `${PLACEHOLDER}${math.length - 1}X`
  })
  let html = renderer.render(guarded)
  math.forEach((expression, index) => {
    html = html.replace(`${PLACEHOLDER}${index}X`, () => escapeHtml(expression))
  })
  return html
}

function visibleText (element) {
  return String(element.textContent || '').replace(/\u200b/g, '')
}

// The TeX behind one rendered formula. Live KaTeX keeps it in the MathML
// annotation; rows saved by earlier versions hold KaTeX after the server
// sanitizer dropped the MathML wrapper, so the glyph text is followed by the
// TeX source inside .katex-mathml.
function katexSource (node) {
  const annotation = node.querySelector('annotation[encoding="application/x-tex"]')
  if (annotation) return annotation.textContent || ''
  const mathml = node.querySelector('.katex-mathml')
  if (!mathml) return ''
  const source = visibleText(mathml)
  const visual = node.querySelector('.katex-html')
  const glyphs = visual ? visibleText(visual) : ''
  if (glyphs && source.startsWith(glyphs) && glyphs.length < source.length) {
    return source.slice(glyphs.length)
  }
  // The split is ambiguous; keep what the reader saw instead of the duplicate.
  return glyphs
}

function revertKatex (root) {
  root.querySelectorAll('.katex').forEach(node => {
    if (node.parentElement && node.parentElement.closest('.katex')) return
    const source = katexSource(node)
    if (!source) return
    const display = Boolean(node.closest('.katex-display'))
    node.replaceWith(root.ownerDocument.createTextNode(display ? `$$${source}$$` : `$${source}$`))
  })
}

// Replace every formula with a placeholder at the text-node level: the text is
// already decoded, so entities never leak into the Markdown as literal `&lt;`.
function protectMath (html) {
  const math = []
  const root = document.createElement('div')
  root.innerHTML = html
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes = []
  while (walker.nextNode()) nodes.push(walker.currentNode)
  nodes.forEach(node => {
    node.nodeValue = node.nodeValue.replace(mathPattern(), expression => {
      math.push(expression)
      return `${PLACEHOLDER}${math.length - 1}X`
    })
  })
  return { html: root.innerHTML, math }
}

export function htmlToMarkdown (value, turndown) {
  let content = String(value || '')
  if (!/<[a-z][\s\S]*>/i.test(content)) return content
  if (typeof document !== 'undefined' && /katex/i.test(content)) {
    const root = document.createElement('div')
    root.innerHTML = content
    if (root.querySelector('.katex')) {
      revertKatex(root)
      content = root.innerHTML
    }
  }
  content = DOMPurify.sanitize(content)
  const { html, math } = protectMath(content)
  let markdown = turndown.turndown(html)
  math.forEach((expression, index) => {
    markdown = markdown.replace(`${PLACEHOLDER}${index}X`, () => expression)
  })
  return markdown
}
