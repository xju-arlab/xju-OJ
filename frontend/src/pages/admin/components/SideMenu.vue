<template>
  <el-menu class="vertical_menu"
           :router="true" :default-active="currentPath">
    <div class="logo"><span class="brand-mark">XJ</span><strong>XJU-OJ</strong><small>管理后台</small></div>
    <el-menu-item index="/"><Icon type="dashboard" />{{$t('m.Dashboard')}}</el-menu-item>
    <el-sub-menu v-if="isSuperAdmin" index="general">
      <template #title><Icon type="menu" />{{$t('m.General')}}</template>
      <el-menu-item index="/user">{{$t('m.User')}}</el-menu-item>
      <el-menu-item index="/announcement">{{$t('m.Announcement')}}</el-menu-item>
      <el-menu-item index="/judge-server">{{$t('m.Judge_Server')}}</el-menu-item>
      <el-menu-item index="/prune-test-case">{{$t('m.Prune_Test_Case')}}</el-menu-item>
    </el-sub-menu>
    <el-sub-menu index="problem" v-if="hasProblemPermission">
      <template #title><Icon type="bars" />{{$t('m.Problem')}}</template>
      <el-menu-item index="/problems">{{$t('m.Problem_List')}}</el-menu-item>
      <el-menu-item index="/problem/create">{{$t('m.Create_Problem')}}</el-menu-item>
      <el-menu-item index="/problem/batch_ops">{{$t('m.Export_Import_Problem')}}</el-menu-item>

    </el-sub-menu>
    <el-sub-menu index="contest">
      <template #title><Icon type="trophy" />{{$t('m.Contest')}}</template>
      <el-menu-item index="/contest">{{$t('m.Contest_List')}}</el-menu-item>
      <el-menu-item index="/contest/create">{{$t('m.Create_Contest')}}</el-menu-item>
    </el-sub-menu>
    <el-sub-menu v-if="hasProblemPermission" index="ai-problem">
      <template #title><Icon type="ios-analytics" />AI 题库</template>
      <el-menu-item index="/ai/problems">题目管理</el-menu-item>
      <el-menu-item index="/ai/problem/batch_ops">导入 / 导出</el-menu-item>
    </el-sub-menu>
  </el-menu>
</template>
<script>
  import {mapGetters} from '@/store/compat'

  export default {
    name: 'SideMenu',
    computed: {
      currentPath () { return this.$route.path },
      ...mapGetters(['user', 'isSuperAdmin', 'hasProblemPermission'])
    }
  }
</script>

<style scoped lang="less">
  .vertical_menu {
    overflow: auto;
    width: 205px;
    height: 100%;
    position: fixed !important;
    z-index: 100;
    top: 0;
    bottom: 0;
    left: 0;
    background: var(--color-bg);
    border-right: 1px solid var(--color-border);
    .logo { display: flex; align-items: center; gap: 9px; margin: 0; padding: 18px 16px 20px; color: var(--color-text); }
    .logo strong { font-size: 17px; }.logo small { margin-left: auto; color: var(--color-text-faint); font-size: 11px; }
    .brand-mark { display: inline-grid; width: 30px; height: 30px; place-items: center; border-radius: var(--radius-sm); background: var(--color-text); color: #fff; font-size: 11px; }
    :deep(.el-menu-item), :deep(.el-sub-menu__title) { display: flex; align-items: center; min-height: 40px; height: 40px; line-height: 1; margin: 2px 10px; padding: 0 12px !important; border-radius: var(--radius-sm); }
    :deep(.el-menu-item.is-active) { background: var(--color-bg-subtle); }
    :deep(.legacy-icon), :deep(.el-icon) { display: inline-flex; flex: none; align-items: center; justify-content: center; margin-right: 8px; vertical-align: middle; }
  }
</style>
