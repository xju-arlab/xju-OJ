import { camelize, h, ref, toHandlerKey } from 'vue'
import ElementPlus, {
  ElAlert, ElBacktop, ElButton, ElButtonGroup, ElCard, ElCarousel, ElCarouselItem, ElCol, ElDialog,
  ElDropdown, ElDropdownItem, ElDropdownMenu, ElForm, ElFormItem, ElInput, ElLoading, ElMenu, ElMenuItem,
  ElMessage, ElMessageBox, ElNotification, ElOption, ElPagination, ElPopover, ElProgress, ElRow, ElSelect,
  ElSubMenu, ElSwitch, ElTable, ElTableColumn, ElTag, ElTooltip, ElUpload
} from 'element-plus'
import 'element-plus/dist/index.css'
import { resolveIcon } from './icon-map'

const forward = (component, name, map = {}) => ({
  name,
  inheritAttrs: false,
  emits: ['input', 'update:modelValue', 'on-change', 'on-click', 'on-select', 'on-enter', 'on-page-size-change'],
  setup (_, { attrs, slots, emit }) {
    return () => h(component, {
      ...attrs,
      ...(attrs.value !== undefined && attrs.modelValue === undefined ? { modelValue: attrs.value } : {}),
      'onUpdate:modelValue': value => { emit('update:modelValue', value); emit('input', value) },
      onChange: value => emit('on-change', value),
      onCommand: value => emit(map.command || 'on-click', value),
      onSelect: value => emit(map.select || 'on-select', value),
      onKeyup: event => { if (event.key === 'Enter') emit('on-enter', event) },
      onSizeChange: value => emit('on-page-size-change', value),
      onCurrentChange: value => emit('on-change', value)
    }, slots)
  }
})

const LegacyIcon = {
  name: 'Icon',
  props: { type: String, size: [String, Number], color: String },
  setup (props) {
    return () => h('i', {
      class: ['legacy-icon', props.type],
      style: { fontSize: props.size ? `${props.size}px` : undefined, color: props.color }
    }, [h(resolveIcon(props.type), { size: props.size || 16, strokeWidth: 1.75 })])
  }
}

const LegacyButton = {
  name: 'LegacyButton',
  inheritAttrs: false,
  props: { type: String, shape: String, long: Boolean },
  setup (props, { attrs, slots }) {
    const allowedTypes = new Set(['primary', 'success', 'warning', 'info', 'danger', 'text'])
    return () => h(ElButton, {
      ...attrs,
      type: allowedTypes.has(props.type) ? props.type : '',
      plain: props.type === 'ghost' || attrs.plain,
      text: props.type === 'text' || attrs.text,
      round: props.shape === 'circle' || attrs.round,
      style: [attrs.style, props.long ? { width: '100%' } : null]
    }, slots)
  }
}

const LegacyAlert = {
  name: 'Alert',
  inheritAttrs: false,
  setup (_, { attrs, slots }) {
    return () => h(ElAlert, attrs, {
      title: slots.default,
      default: slots.desc
    })
  }
}

const LegacyCard = {
  name: 'Card',
  inheritAttrs: false,
  props: { padding: [String, Number], shadow: Boolean, disHover: Boolean, bordered: { type: Boolean, default: true } },
  setup (props, { attrs, slots }) {
    return () => h(ElCard, {
      ...attrs,
      shadow: props.shadow ? 'always' : (props.disHover ? 'never' : 'hover'),
      bodyStyle: props.padding === undefined ? undefined : { padding: typeof props.padding === 'number' ? `${props.padding}px` : props.padding },
      class: [attrs.class, { 'legacy-card-borderless': !props.bordered }]
    }, {
      header: slots.title || slots.extra ? () => [slots.title?.(), slots.extra?.()] : undefined,
      default: slots.default
    })
  }
}

const LegacyPoptip = {
  name: 'Poptip',
  inheritAttrs: false,
  setup (_, { attrs, slots }) {
    return () => h(ElPopover, attrs, {
      reference: slots.default,
      default: slots.content
    })
  }
}

const LegacySwitch = {
  name: 'iSwitch',
  inheritAttrs: false,
  props: { modelValue: { type: Boolean, default: undefined }, value: { type: Boolean, default: undefined } },
  emits: ['input', 'update:modelValue', 'on-change'],
  setup (props, { attrs, slots, emit }) {
    return () => h(ElSwitch, {
      ...attrs,
      modelValue: props.modelValue ?? props.value ?? false,
      'onUpdate:modelValue': value => { emit('update:modelValue', value); emit('input', value) },
      onChange: value => emit('on-change', value)
    }, {
      'active-action': slots.open,
      'inactive-action': slots.close
    })
  }
}

const LegacyCarousel = {
  name: 'Carousel',
  inheritAttrs: false,
  props: { modelValue: { type: Number, default: undefined }, value: { type: Number, default: undefined } },
  emits: ['input', 'update:modelValue', 'on-change'],
  setup (props, { attrs, slots, emit }) {
    return () => h(ElCarousel, {
      ...attrs,
      initialIndex: props.modelValue ?? props.value ?? 0,
      interval: attrs.autoplaySpeed,
      onChange: (value, previous) => { emit('update:modelValue', value); emit('input', value); emit('on-change', value, previous) }
    }, slots)
  }
}

const LegacyUpload = {
  name: 'Upload',
  inheritAttrs: false,
  props: { type: String },
  setup (props, { attrs, slots }) {
    return () => h(ElUpload, { ...attrs, drag: props.type === 'drag' }, slots)
  }
}

const LegacyMenu = {
  name: 'Menu',
  inheritAttrs: false,
  props: { activeName: [String, Number] },
  emits: ['on-select', 'select'],
  setup (props, { attrs, slots, emit }) {
    return () => h(ElMenu, {
      ...attrs,
      defaultActive: props.activeName,
      onSelect: (...args) => { emit('on-select', ...args); emit('select', ...args) }
    }, slots)
  }
}

const legacyIndexItem = (component, name) => ({
  name,
  inheritAttrs: false,
  props: { name: [String, Number] },
  setup (props, { attrs, slots }) {
    return () => h(component, { ...attrs, index: props.name }, slots)
  }
})

const LegacyMenuItem = legacyIndexItem(ElMenuItem, 'MenuItem')
const LegacySubmenu = legacyIndexItem(ElSubMenu, 'Submenu')

const LegacyDropdown = {
  name: 'Dropdown',
  inheritAttrs: false,
  emits: ['on-click', 'command'],
  setup (_, { attrs, slots, emit }) {
    return () => h(ElDropdown, {
      ...attrs,
      onCommand: value => { emit('on-click', value); emit('command', value) }
    }, {
      default: slots.default,
      dropdown: slots.list || slots.dropdown
    })
  }
}

const LegacyDropdownItem = {
  name: 'DropdownItem',
  inheritAttrs: false,
  props: { name: [String, Number] },
  setup (props, { attrs, slots }) {
    return () => h(ElDropdownItem, { ...attrs, command: props.name }, slots)
  }
}

const LegacyForm = {
  name: 'Form',
  inheritAttrs: false,
  setup (_, { attrs, slots, expose }) {
    const form = ref()
    const call = method => (...args) => form.value?.[method](...args)
    expose({
      validate: call('validate'),
      validateField: call('validateField'),
      resetFields: call('resetFields'),
      clearValidate: call('clearValidate'),
      scrollToField: call('scrollToField')
    })
    return () => h(ElForm, { ...attrs, ref: form }, slots)
  }
}
const LegacyFormItem = forward(ElFormItem, 'FormItem')

const legacyRenderComponents = {
  Alert: ElAlert,
  Button: LegacyButton,
  Card: ElCard,
  Col: ElCol,
  Form: LegacyForm,
  FormItem: LegacyFormItem,
  Icon: LegacyIcon,
  Input: ElInput,
  Option: ElOption,
  Progress: ElProgress,
  Row: ElRow,
  Select: ElSelect,
  Switch: ElSwitch,
  Tag: ElTag,
  Tooltip: ElTooltip
}

const normalizeLegacyData = data => {
  if (!data || Array.isArray(data) || typeof data !== 'object' || data.__v_isVNode) return data
  const { attrs, domProps, nativeOn, on, props, scopedSlots, ...rest } = data
  const normalized = { ...rest, ...attrs, ...domProps, ...props }
  for (const events of [nativeOn, on]) {
    for (const [event, handler] of Object.entries(events || {})) {
      normalized[toHandlerKey(camelize(event))] = handler
    }
  }
  if (scopedSlots) normalized.__legacySlots = scopedSlots
  return normalized
}

function legacyH (type, data, children) {
  const component = typeof type === 'string' ? (legacyRenderComponents[type] || type) : type
  if (arguments.length === 2 && (Array.isArray(data) || typeof data !== 'object' || data?.__v_isVNode)) {
    children = data
    data = null
  }
  const normalized = normalizeLegacyData(data)
  const legacySlots = normalized?.__legacySlots
  if (legacySlots) delete normalized.__legacySlots
  if (legacySlots) return h(component, normalized, legacySlots)
  if (component !== type && children !== undefined) return h(component, normalized, { default: () => children })
  return h(component, normalized, children)
}

const LegacyTable = {
  name: 'Table',
  inheritAttrs: false,
  props: { columns: { type: Array, default: () => [] }, data: { type: Array, default: () => [] } },
  setup (props, { attrs, slots }) {
    return () => h(ElTable, {
      ...attrs,
      data: props.data,
      cellClassName: attrs.cellClassName || (({ row, column }) => row.cellClassName?.[column.property] || '')
    }, {
      default: () => props.columns.map((column, index) => h(ElTableColumn, {
        key: column.key || index,
        prop: column.key,
        label: column.title,
        width: column.width,
        minWidth: column.minWidth,
        className: column.className,
        align: column.align,
        fixed: column.fixed,
        sortable: column.sortable
      }, {
        header: scope => column.renderHeader
          ? column.renderHeader(legacyH, { ...scope, column })
          : String(column.title ?? ''),
        default: scope => column.render
          ? column.render(legacyH, { row: scope.row, index: scope.$index, column })
          : (slots[column.slot] ? slots[column.slot](scope) : String(scope.row[column.key] ?? ''))
      }))
    })
  }
}

const LegacyPagination = {
  name: 'Page', inheritAttrs: false,
  props: { total: Number, current: { type: Number, default: 1 }, pageSize: { type: Number, default: 10 }, showSizer: Boolean },
  emits: ['on-change', 'on-page-size-change', 'update:current', 'update:page-size'],
  setup (props, { attrs, emit }) {
    return () => h(ElPagination, {
      ...attrs, total: props.total, currentPage: props.current, pageSize: props.pageSize,
      layout: props.showSizer ? 'total, sizes, prev, pager, next' : 'total, prev, pager, next',
      'onUpdate:currentPage': value => { emit('update:current', value); emit('on-change', value) },
      'onUpdate:pageSize': value => { emit('update:page-size', value); emit('on-page-size-change', value) }
    })
  }
}

const LegacyModal = {
  name: 'Modal', inheritAttrs: false,
  props: {
    modelValue: { type: Boolean, default: undefined }, value: { type: Boolean, default: undefined },
    visible: { type: Boolean, default: undefined }, title: String, width: [String, Number]
  },
  emits: ['input', 'update:modelValue', 'update:visible', 'on-ok', 'on-cancel'],
  setup (props, { attrs, slots, emit }) {
    return () => h(ElDialog, {
      ...attrs, modelValue: props.visible ?? props.modelValue ?? props.value, title: props.title,
      width: typeof props.width === 'number' ? `${props.width}px` : props.width,
      'onUpdate:modelValue': value => { emit('update:modelValue', value); emit('update:visible', value); emit('input', value); if (!value) emit('on-cancel') }
    }, { default: slots.default, footer: slots.footer, header: slots.header })
  }
}

const aliases = {
  Alert: LegacyAlert, BackTop: ElBacktop, LegacyButton, ButtonGroup: ElButtonGroup, Card: LegacyCard,
  Carousel: LegacyCarousel, CarouselItem: ElCarouselItem, Col: ElCol, Dropdown: LegacyDropdown,
  DropdownItem: LegacyDropdownItem, 'Dropdown-item': LegacyDropdownItem, DropdownMenu: ElDropdownMenu, 'Dropdown-menu': ElDropdownMenu,
  Form: LegacyForm, FormItem: LegacyFormItem, 'Form-item': LegacyFormItem, Icon: LegacyIcon, Input: forward(ElInput, 'Input'),
  Menu: LegacyMenu, MenuItem: LegacyMenuItem, 'Menu-item': LegacyMenuItem,
  Modal: LegacyModal, LegacyDialog: LegacyModal, Option: ElOption, Page: LegacyPagination, Poptip: LegacyPoptip, Progress: ElProgress,
  Row: ElRow, Select: forward(ElSelect, 'Select'), Spin: { name: 'Spin', setup: () => () => h('div', { class: 'legacy-spin' }, 'Loading…') },
  Submenu: LegacySubmenu, Switch: LegacySwitch, 'i-switch': LegacySwitch,
  Table: LegacyTable, Tag: ElTag, Tooltip: ElTooltip, Upload: LegacyUpload
}

const confirm = (options = {}) => {
  const { onOk, onCancel, okText, cancelText, content, message, title, ...messageBoxOptions } = options
  return ElMessageBox.confirm(content || message || '', title || 'Confirm', {
    ...messageBoxOptions,
    confirmButtonText: okText || messageBoxOptions.confirmButtonText,
    cancelButtonText: cancelText || messageBoxOptions.cancelButtonText
  }).then(result => Promise.resolve(onOk?.()).then(() => result), reason => {
    onCancel?.()
    return reason
  })
}

export default {
  install (app, { i18n } = {}) {
    app.use(ElementPlus)
    Object.entries(aliases).forEach(([name, component]) => app.component(name, component))
    const globals = app.config.globalProperties
    globals.$Message = { config: () => {}, error: ElMessage.error, info: ElMessage.info, success: ElMessage.success, warning: ElMessage.warning }
    const alert = options => ElMessageBox.alert(options.content || '', options.title || '')
    globals.$Modal = { confirm, success: alert, info: alert, warning: alert, error: alert }
    globals.$Notice = ElNotification
    let loading
    const finishLoading = () => { if (loading) loading.close(); loading = null }
    globals.$Loading = { start: () => { if (!loading) loading = ElLoading.service({ fullscreen: true }) }, finish: finishLoading, error: finishLoading }
    globals.$message = ElMessage
    globals.$confirm = (message, title, options) => ElMessageBox.confirm(message, title, options)
    if (i18n) globals.$t = (...args) => i18n.global.t(...args)
  }
}
