import { createApp, h, reactive } from 'vue'
import CodeMirror from '../../src/shared/editors/CodeMirrorAdapter.vue'
import RichText from '../../src/shared/editors/RichTextEditorAdapter.vue'
import Highlight from '../../src/plugins/highlight.js'
import Katex from '../../src/plugins/katex.js'
import LegacyUI from '../../src/shared/ui/legacy-ui.js'
import storage from '../../src/utils/storage.js'

const state = reactive({ code: 'int main() {}', rich: '<p>Formula $a+b$</p>', richChanges: 0, highlight: 'int answer = 1;' })
const app = createApp({
  render: () => h('main', [
    h(CodeMirror, { modelValue: state.code, 'onUpdate:modelValue': value => { state.code = value } }),
    h(RichText, { modelValue: state.rich, 'onUpdate:modelValue': value => { state.rich = value; state.richChanges++ } })
  ])
})
app.use(Highlight).use(Katex).use(LegacyUI).mount('#fixture')
window.fixture = { state, storage, globals: app.config.globalProperties }
