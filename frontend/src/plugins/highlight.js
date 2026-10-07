let highlighterPromise

const getHighlighter = () => highlighterPromise || (highlighterPromise = Promise.all([
  import('highlight.js/lib/core'),
  import('highlight.js/lib/languages/cpp'),
  import('highlight.js/lib/languages/python'),
  import('highlight.js/lib/languages/java'),
  import('highlight.js/styles/base16/solarized-light.css')
]).then(([core, cpp, python, java]) => {
  const hljs = core.default
  hljs.registerLanguage('cpp', cpp.default)
  hljs.registerLanguage('java', java.default)
  hljs.registerLanguage('python', python.default)
  return hljs
}))

const render = async (el, binding) => {
  const hljs = await getHighlighter()
  if (!el.isConnected) return
  Array.from(el.querySelectorAll('pre code')).forEach(target => {
    if (binding.value !== undefined) target.textContent = binding.value ?? ''
    delete target.dataset.highlighted
    hljs.highlightElement(target)
  })
}
export default { install (app) { app.directive('highlight', { mounted: render, updated: render }) } }
