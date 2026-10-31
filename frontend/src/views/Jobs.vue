<template>
  <el-card>
    <div class="toolbar-row">
      <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap">
        <el-input
          v-model="keyword"
          placeholder="搜索作业名"
          style="width: 280px"
          clearable
          @keyup.enter="loadJobs"
        >
          <template #append>
            <el-button @click="loadJobs">
              <el-icon><Search /></el-icon>
            </el-button>
          </template>
        </el-input>
        <el-button
          v-if="selectedJobs.length"
          type="danger"
          @click="batchDeleteConfirm"
          :loading="batchDeleting"
        >
          <el-icon><Delete /></el-icon> 批量删除 ({{ selectedJobs.length }})
        </el-button>
      </div>
    </div>

    <el-table
      :data="jobs"
      border
      stripe
      @row-click="showDetail"
      highlight-current-row
      @selection-change="onSelectionChange"
      v-loading="loading"
    >
      <el-table-column type="selection" width="45" align="center" />
      <el-table-column label="作业名" min-width="180">
        <template #default="{ row }">
          <el-link type="primary" @click.stop="showDetail(row)">{{ row.job_name }}</el-link>
        </template>
      </el-table-column>
      <el-table-column prop="job_type" label="类型" width="100" align="center" />
      <el-table-column label="源表数" width="80" align="center">
        <template #default="{ row }">
          <el-link v-if="row.source_count" type="primary" @click.stop="showDetail(row, 'source')">{{ row.source_count }}</el-link>
          <span v-else>0</span>
        </template>
      </el-table-column>
      <el-table-column label="目标表数" width="90" align="center">
        <template #default="{ row }">
          <el-link v-if="row.target_count" type="primary" @click.stop="showDetail(row, 'target')">{{ row.target_count }}</el-link>
          <span v-else>0</span>
        </template>
      </el-table-column>
      <el-table-column label="字段映射数" width="100" align="center">
        <template #default="{ row }">
          <el-link v-if="row.field_mapping_count" type="primary" @click.stop="showDetail(row, 'field')">{{ row.field_mapping_count }}</el-link>
          <span v-else>0</span>
        </template>
      </el-table-column>
      <el-table-column label="上下游数" width="90" align="center">
        <template #default="{ row }">
          <el-link v-if="(row.upstream_count || 0) + (row.downstream_count || 0)" type="primary" @click.stop="showDetail(row, 'lineage')">
            {{ (row.upstream_count || 0) + (row.downstream_count || 0) }}
          </el-link>
          <span v-else>0</span>
        </template>
      </el-table-column>
      <el-table-column prop="sp_name" label="存储过程" min-width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="120" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click.stop="openEditDialog(row)">
            <el-icon><Edit /></el-icon>
          </el-button>
          <el-popconfirm title="确定删除该作业?" @confirm="deleteJob(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link @click.stop>
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 作业详情抽屉 -->
    <el-drawer v-model="drawerVisible" size="33%" :title="detail?.job_name || '作业详情'">
      <div v-if="detailLoading" style="text-align: center; padding: 40px">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <p>加载中...</p>
      </div>
      <div v-else-if="detail">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="基本信息" name="info">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="作业名">{{ detail.job_name }}</el-descriptions-item>
              <el-descriptions-item label="SP名" v-if="detail.sp_name">
                <el-tag type="info">{{ detail.sp_name }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="类型">{{ detail.job_type || '-' }}</el-descriptions-item>
              <el-descriptions-item label="描述">
                <pre style="margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit">{{ detail.description || '-' }}</pre>
              </el-descriptions-item>
              <el-descriptions-item label="调度">{{ detail.schedule || '-' }}</el-descriptions-item>
              <el-descriptions-item label="负责人">{{ detail.owner || '-' }}</el-descriptions-item>
              <el-descriptions-item label="导入批次">{{ detail.import_batch || '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>
          <el-tab-pane label="源表" name="source">
            <el-table :data="detail?.source_tables" border size="small" empty-text="无数据">
              <el-table-column prop="table_name" label="表名" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="目标表" name="target">
            <el-table :data="detail?.target_tables" border size="small" empty-text="无数据">
              <el-table-column prop="table_name" label="表名" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="字段映射" name="field">
            <el-table :data="detail?.field_mappings" border size="small" empty-text="无数据">
              <el-table-column prop="source_table" label="源表" min-width="120" show-overflow-tooltip />
              <el-table-column prop="source_field" label="源字段" min-width="100" show-overflow-tooltip />
              <el-table-column prop="target_table" label="目标表" min-width="120" show-overflow-tooltip />
              <el-table-column prop="target_field" label="目标字段" min-width="100" show-overflow-tooltip />
              <el-table-column prop="operation" label="操作" width="90" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.operation" size="small" :type="operationTagType(row.operation)">{{ row.operation }}</el-tag>
                  <span v-else style="color: #ccc">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="source" label="来源" width="80" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.source === 'sp' ? 'warning' : ''">{{ row.source === 'sp' ? 'SP' : 'Excel' }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="上下游" name="lineage">
            <div style="margin-bottom: 16px">
              <strong>上游作业 ({{ detail?.upstream?.length || 0 }})</strong>
              <div v-if="detail?.upstream?.length" style="margin-top: 8px">
                <div v-for="u in detail.upstream" :key="u.job_id" style="padding: 3px 0">
                  <el-link type="primary" @click="navigateToJob(u.job_id)">{{ u.job_name }}</el-link>
                </div>
              </div>
              <div v-else style="color: #999; margin-top: 8px">无</div>
            </div>
            <div>
              <strong>下游作业 ({{ detail?.downstream?.length || 0 }})</strong>
              <div v-if="detail?.downstream?.length" style="margin-top: 8px">
                <div v-for="d in detail.downstream" :key="d.job_id" style="padding: 3px 0">
                  <el-link type="success" @click="navigateToJob(d.job_id)">{{ d.job_name }}</el-link>
                </div>
              </div>
              <div v-else style="color: #999; margin-top: 8px">无</div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>

    <!-- 编辑作业对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑作业" width="500px">
      <el-form label-width="80px" v-if="editForm">
        <el-form-item label="作业名">
          <el-input v-model="editForm.job_name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="editForm.job_type" style="width: 100%">
            <el-option label="ETL" value="ETL" />
            <el-option label="PROCEDURE" value="PROCEDURE" />
            <el-option label="SCRIPT" value="SCRIPT" />
            <el-option label="OTHER" value="OTHER" />
          </el-select>
        </el-form-item>
        <el-form-item label="SP名">
          <el-input v-model="editForm.sp_name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="调度">
          <el-input v-model="editForm.schedule" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Delete, Edit, Loading } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const store = useAppStore()
const route = useRoute()
const router = useRouter()
const keyword = ref('')
const jobs = ref<any[]>([])
const selectedJobs = ref<any[]>([])
const batchDeleting = ref(false)
const loading = ref(false)
const drawerVisible = ref(false)
const detail = ref<any>(null)
const detailLoading = ref(false)
const activeTab = ref('info')
const editDialogVisible = ref(false)
const editForm = ref<any>(null)
const editJobId = ref('')
const saving = ref(false)

onMounted(async () => {
  await loadJobs()
  const jobId = route.query.jobId as string
  if (jobId) await showDetailById(jobId)
})

watch(() => store.wsVersion, () => loadJobs())

function onSelectionChange(rows: any[]) {
  selectedJobs.value = rows
}

async function loadJobs() {
  if (!store.currentWorkspace) return
  loading.value = true
  try {
    jobs.value = await api.get(`/jobs/list/${store.currentWorkspace.id}`, { params: { keyword: keyword.value } })
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function showDetail(row: any, tab?: string) {
  if (tab) activeTab.value = tab
  else activeTab.value = 'info'
  await showDetailById(row.id)
}

async function showDetailById(jobId: string) {
  if (!store.currentWorkspace) return
  drawerVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await api.get(`/jobs/detail/${store.currentWorkspace.id}/${jobId}`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载详情失败')
  } finally {
    detailLoading.value = false
  }
}

function navigateToJob(jobId: string) {
  showDetailById(jobId)
}

function openEditDialog(row: any) {
  editJobId.value = row.id
  editForm.value = {
    job_name: row.job_name || '',
    job_type: row.job_type || '',
    sp_name: row.sp_name || '',
    description: row.description || '',
    schedule: row.schedule || '',
  }
  editDialogVisible.value = true
}

async function saveEdit() {
  if (!store.currentWorkspace || !editForm.value) return
  saving.value = true
  try {
    await api.put(`/jobs/${store.currentWorkspace.id}/${editJobId.value}`, editForm.value)
    ElMessage.success('保存成功')
    editDialogVisible.value = false
    await loadJobs()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteJob(jobId: string) {
  if (!store.currentWorkspace) return
  try {
    await api.delete(`/jobs/${store.currentWorkspace.id}/${jobId}`)
    ElMessage.success('删除成功')
    drawerVisible.value = false
    await loadJobs()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function batchDeleteConfirm() {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedJobs.value.length} 个作业吗？此操作不可撤销。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  batchDeleting.value = true
  try {
    const ids = selectedJobs.value.map(j => j.id)
    await api.post(`/jobs/batch-delete/${store.currentWorkspace!.id}`, ids)
    ElMessage.success(`成功删除 ${ids.length} 个作业`)
    selectedJobs.value = []
    drawerVisible.value = false
    await loadJobs()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '批量删除失败')
  } finally {
    batchDeleting.value = false
  }
}

function operationTagType(op: string) {
  const map: Record<string, string> = { INSERT: 'success', UPDATE: 'warning', MERGE: 'primary' }
  return map[op?.toUpperCase()] || 'info'
}
</script>
