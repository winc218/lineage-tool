<template>
  <div>
    <!-- 统计卡片 -->
    <el-row :gutter="20">
      <el-col :span="6" v-for="card in cards" :key="card.key">
        <el-card
          shadow="hover"
          :body-style="{ padding: '20px' }"
          class="stat-card"
          @click="card.route ? $router.push(card.route) : null"
          :class="{ clickable: !!card.route }"
        >
          <div class="stat-card-inner">
            <div class="stat-info">
              <div class="stat-label">{{ card.label }}</div>
              <div class="num">{{ card.value }}</div>
            </div>
            <div class="stat-icon" :style="{ background: card.color + '15' }">
              <el-icon :size="28" :color="card.color">
                <component :is="card.icon" />
              </el-icon>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 快捷操作 + 工作空间信息 -->
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span class="page-title">快捷操作</span></template>
          <div class="quick-actions">
            <el-button type="primary" @click="$router.push('/import')">
              <el-icon><Upload /></el-icon>&nbsp;导入 Excel
            </el-button>
            <el-button @click="$router.push('/graph')">
              <el-icon><Connection /></el-icon>&nbsp;查看血缘图
            </el-button>
            <el-button @click="$router.push('/sp')">
              <el-icon><Check /></el-icon>&nbsp;SP 校验
            </el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span class="page-title">当前工作空间</span></template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="名称">{{ store.currentWorkspace?.name }}</el-descriptions-item>
            <el-descriptions-item label="描述">{{ store.currentWorkspace?.description || '-' }}</el-descriptions-item>
            <el-descriptions-item label="我的角色">{{ roleLabel }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Upload, Connection, Check, Document, DataAnalysis, Warning, Files } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const store = useAppStore()
const stats = ref<any>({})

const roleLabel = computed(() => {
  const r = store.currentWorkspace?.role
  if (r === 'OWNER') return '所有者'
  if (r === 'EDITOR') return '编辑者'
  if (r === 'VIEWER') return '只读'
  return ''
})

const cards = computed(() => [
  {
    key: 'jobs',
    label: '作业总数',
    value: stats.value.total_jobs || 0,
    icon: Document,
    color: '#1a5fab',
    route: { name: 'jobs' },
  },
  {
    key: 'sp_matched',
    label: 'SP 已匹配',
    value: stats.value.sp_matched || 0,
    icon: Files,
    color: '#e6a23c',
    route: { name: 'sp' },
  },
  {
    key: 'parse_success',
    label: '解析成功',
    value: stats.value.parse_success || 0,
    icon: DataAnalysis,
    color: '#67c23a',
    route: { name: 'sp' },
  },
  {
    key: 'diffs_pending',
    label: '待处理差异',
    value: stats.value.diffs_pending || 0,
    icon: Warning,
    color: '#f56c6c',
    route: { name: 'sp', query: { tab: 'diffs' } },
  },
])

async function loadStats() {
  if (!store.currentWorkspace) return
  try {
    stats.value = await api.get(`/sp/overview/${store.currentWorkspace.id}`)
  } catch {
    stats.value = {}
  }
}

onMounted(loadStats)

// 工作空间切换时自动刷新
watch(() => store.wsVersion, loadStats)
</script>

<style scoped>
.stat-card {
  margin-bottom: 4px;
  transition: all 0.2s;
}
.stat-card.clickable {
  cursor: pointer;
}
.stat-card.clickable:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
}
.stat-card-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.stat-info {
  flex: 1;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}
.num {
  font-size: 30px;
  font-weight: bold;
  color: #1a5fab;
  line-height: 1.2;
}
.stat-icon {
  width: 52px;
  height: 52px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.quick-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
</style>
