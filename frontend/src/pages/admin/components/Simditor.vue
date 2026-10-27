<template><RichTextEditorAdapter :value="content" :image-upload="imageUpload" :compact="compact" :placeholder="placeholder" @input="onInput" @upload="$emit('upload', $event)" /></template>
<script>
import RichTextEditorAdapter from '@/shared/editors/RichTextEditorAdapter.vue'
export default {
  name: 'Simditor', components: { RichTextEditorAdapter },
  props: { toolbar: { type: Array, default: () => [] }, value: { type: String, default: '' }, modelValue: { type: String, default: undefined }, imageUpload: { type: Object, default: null }, compact: { type: Boolean, default: false }, placeholder: { type: String, default: '' } },
  computed: { content () { return this.modelValue === undefined ? this.value : this.modelValue } },
  emits: ['change', 'input', 'update:value', 'update:modelValue', 'upload'],
  methods: { onInput (value) { this.$emit('change', value); this.$emit('input', value); this.$emit('update:value', value); this.$emit('update:modelValue', value) } }
}
</script>
