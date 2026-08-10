<template>
  <el-card>
    <div class="toolbar-row">
      <div style="display: flex; align-items: center; gap: 12px">
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
      </div>
    </div>

    <el-table :data="jobs" border stripe @row-click="showDetail" highlight-current-row>
      <el-table-column prop="job_name" label="作业名" min-width="180" />
      <el-table-column prop="job_type" label="类型" width="100" align="center" />
      <el-table-column prop="owner" label="负责人" width="100" align="center" />
      <el-table-column prop="sp_name" label="存储过程" min-width="180" show-overflow-tooltip />
    </el-table>

    <el-drawer v-model="drawerVisible" size="520px" :title="detail?.job_name || '作业详情'">
      <el-tabs>
        <el-tab-pane label="基本信息">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="作业名">{{ detail?.job_name }}</el-descriptions-item>
            <el-descriptions-item label="类型">{{ detail?.job_type }}</el-descriptions-item>
            <el-descriptions-item label="描述">{{ detail?.description }}</el-descriptions-item>
            <el-descriptions-item label="SP名">{{ detail?.sp_name }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
        <el-tab-pane label="源表">
          <el-table :data="detail?.source_tables" border size="small" empty-text="无数据">
            <el-table-column prop="table_name" label="表名" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="目标表">
          <el-table :data="detail?.target_tables" border size="small" empty-text="无数据">
            <el-table-column prop="table_name" label="表名" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="字段映射">
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
        <el-tab-pane label="上下游">
          <div style="margin-bottom: 16px">
            <strong>上游作业</strong>
            <div v-if="detail?.upstream?.length" style="margin-top: 8px">
              <el-tag v-for="u in detail.upstream" :key="u.job_id" style="margin: 4px 8px 4px 0" type="info">
                {{ u.job_name }}
              </el-tag>
            </div>
            <div v-else style="color: #999; margin-top: 8px">无</div>
          </div>
          <div>
            <strong>下游作业</strong>
            <div v-if="detail?.downstream?.length" style="margin-top: 8px">
              <el-tag v-for="d in detail.downstream" :key="d.job_id" style="margin: 4px 8px 4px 0" type="success">
                {{ d.job_name }}
              </el-tag>
            </div>
            <div v-else style="color: #999; margin-top: 8px">无</div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-drawer>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const store = useAppStore()
const route = useRoute()
const keyword = ref('')
const jobs = ref<any[]>([])
const drawerVisible = ref(false)
const detail = ref<any>(null)

onMounted(async () => {
  await loadJobs()
  const jobId = route.query.jobId as string
  if (jobId) await showDetailById(jobId)
})

// 工作空间切换时自动刷新
watch(() => store.wsVersion, () => loadJobs())

async function loadJobs() {
  if (!store.currentWorkspace) return
  jobs.value = await api.get(`/jobs/list/${store.currentWorkspace.id}`, { params: { keyword: keyword.value } })
}

async function showDetail(row: any) {
  await showDetailById(row.id)
}

async function showDetailById(jobId: string) {
  if (!store.currentWorkspace) return
  detail.value = await api.get(`/jobs/detail/${store.currentWorkspace.id}/${jobId}`)
  drawerVisible.value = true
}

function operationTagType(op: string) {
  const map: Record<string, string> = { INSERT: 'success', UPDATE: 'warning', MERGE: 'primary' }
  return map[op?.toUpperCase()] || 'info'
}
</script>
