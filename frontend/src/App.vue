<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
/* ===== 全局样式 ===== */
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

/* 统一 el-main 内部间距 */
.el-main {
  padding: 20px;
  background: #f5f7fa;
}

/* 统一卡片标题对齐和间距 */
.el-card__header {
  padding: 12px 20px;
  font-size: 14px;
}

/* 统一卡片内容间距 */
.el-card__body {
  padding: 20px;
}

/* 页面标题统一 */
.page-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  color: #303133;
}

/* 统一工具栏行 */
.toolbar-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

/* 统一步骤条间距 */
.el-steps {
  margin-bottom: 24px;
}

/* 表格统一紧凑 */
.el-table {
  font-size: 13px;
}

/* 对话框表单统一间距 */
.el-dialog__body {
  padding: 20px 24px;
}

/* 描述列表标签宽度统一 */
.el-descriptions__label {
  width: 100px;
}
</style>
