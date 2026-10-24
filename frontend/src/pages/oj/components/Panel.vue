<template>
  <Card class="feiyue-panel" :padding="padding" :shadow="shadow" :dis-hover="disHover" :bordered="bordered">
    <!-- Without a title or extra content the card renders no header bar. -->
    <template v-if="$slots.title" #title><div class="panel-title">
      <slot name="title"></slot>
    </div></template>
    <template v-if="$slots.extra" #extra><div class="panel-extra">
      <slot name="extra"></slot>
    </div></template>
    <div class="panel-body">
      <slot></slot>
    </div>
  </Card>
</template>
<script>
  export default {
    name: 'Panel',
    props: {
      shadow: {
        required: false,
        type: Boolean,
        default: false
      },
      padding: {
        required: false,
        type: Number,
        default: 0
      },
      disHover: {
        required: false,
        type: Boolean,
        default: false
      },
      bordered: {
        required: false,
        type: Boolean,
        default: true
      }
    }
  }
</script>

<style lang="less">
  @import (reference) '../../../styles/common.less';

  .panel-title {
    .section-title;
    padding: 5px 15px;
  }
  .feiyue-panel { border-radius: var(--radius-md); box-shadow: var(--shadow-card) !important; }
  .feiyue-panel .el-card__header { border-bottom-color: var(--color-border); }

  .panel-extra {
    line-height: 40px;
    .ivu-input-icon {
      line-height: 40px;
    }
    ul.filter {
      > li {
        display: inline-block;
        padding: 0 10px;
      }
    }
  }
  .panel-body {
    word-break: break-all;
    word-wrap: break-word;
  }
</style>
