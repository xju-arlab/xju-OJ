<template>
  <div id="app">
    <router-view></router-view>
  </div>
</template>

<script>
  export default {
    name: 'app',
    components: {}
  }
</script>

<style lang="less">
  body {
    margin: 0;
    padding: 0;
    font-family: var(--font-sans);
    font-size: 14px;
    background-color: var(--color-bg);
  }

  #app {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 100%;
  }
</style>
