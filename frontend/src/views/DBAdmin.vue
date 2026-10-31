<template>
  <el-card>
    <template #header>
      <div style="display: flex; align-items: center; justify-content: space-between">
        <span class="page-title">数据库管理</span>
        <el-tag type="danger">仅 Admin 可访问</el-tag>
      </div>
    </template>

    <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 16px">
      直接操作数据库表可能造成数据不一致，请谨慎操作。
    </el-alert>

    <el-tabs v-model="activeTable" @tab-change="loadTableData">
      <el-tab-pane
        v-for="t in tables"
        :key="t"
        :label="t"
        :name="t"
      />
    </el-tabs>

    <div style="margin-bottom: 12px; display: flex; gap: 12px; align-items: center">
      <el-input
        v-model="sqlQuery"
        placeholder="输入 SQL 查询语句（仅 SELECT）"
        style="flex: 1"
        clearable
        @keyup.enter="executeSql"
      />
      <el-button type="primary" @click="executeSql" :loading="sqlLoading">
        <el-icon><Search /></el-icon> 执行
      </el-button>
      <el-button @click="loadTableData">刷新</el-button>
    </div>

    <el-table
      :data="tableData"
      border
      stripe
      v-loading="loading"
      max-height="500"
      empty-text="暂无数据或执行查询获取结果"
    >
      <el-table-column
        v-for="col in columns"
        :key="col"
        :prop="col"
        :label="col"
        min-width="120"
        show-overflow-tooltip
      />
    </el-table>

    <div style="margin-top: 12px; color: #909399; font-size: 13px">
      共 {{ tableData.length }} 条记录
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const store = useAppStore()
const activeTable = ref('')
const tables = ref<string[]>([])
const tableData = ref<any[]>([])
const columns = ref<string[]>([])
const loading = ref(false)
const sqlQuery = ref('')
const sqlLoading = ref(false)

onMounted(async () => {
  await loadTables()
})

async function loadTables() {
  try {
    tables.value = await api.get('/admin/tables')
    if (tables.value.length) {
      activeTable.value = tables.value[0]
      await loadTableData()
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载表列表失败')
  }
}

async function loadTableData() {
  if (!activeTable.value) return
  loading.value = true
  try {
    const res: any = await api.get(`/admin/tables/${activeTable.value}`)
    tableData.value = res.rows || []
    columns.value = res.columns || []
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载数据失败')
  } finally {
    loading.value = false
  }
}

async function executeSql() {
  if (!sqlQuery.value.trim()) {
    ElMessage.warning('请输入 SQL 语句')
    return
  }
  sqlLoading.value = true
  try {
    const res: any = await api.post('/admin/query', { sql: sqlQuery.value })
    tableData.value = res.rows || []
    columns.value = res.columns || []
    ElMessage.success(`查询返回 ${res.rows?.length || 0} 条记录`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || 'SQL 执行失败')
  } finally {
    sqlLoading.value = false
  }
}
</script>
