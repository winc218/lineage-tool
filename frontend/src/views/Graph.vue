<template>
  <div class="graph-page">
    <div class="toolbar-row">
      <div style="display: flex; align-items: center; gap: 12px">
        <el-input
          v-model="keyword"
          placeholder="搜索作业名"
          style="width: 240px"
          clearable
          @keyup.enter="search"
        />
        <el-button-group>
          <el-button @click="loadGraph">
            <el-icon><Refresh /></el-icon>&nbsp;刷新
          </el-button>
          <el-button @click="autoLayout">
            <el-icon><Rank /></el-icon>&nbsp;自动排列
          </el-button>
          <el-button @click="checkCycles">
            <el-icon><WarnTriangleFilled /></el-icon>&nbsp;环路检测
          </el-button>
          <el-button @click="fitView">
            <el-icon><FullScreen /></el-icon>&nbsp;适应画布
          </el-button>
        </el-button-group>
      </div>
      <el-alert v-if="cycles.length" type="error" :closable="false" show-icon style="flex: 0 1 auto">
        检测到 {{ cycles.length }} 个环路
      </el-alert>
    </div>
    <div ref="graphContainer" class="graph-container" />

    <!-- 作业详情抽屉 -->
    <el-drawer v-model="drawerVisible" size="520px" :title="detail?.job_name || '作业详情'">
      <div v-if="detailLoading" style="text-align: center; padding: 40px">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <p>加载中...</p>
      </div>
      <div v-else-if="detail">
        <el-descriptions :column="1" border size="small" style="margin-bottom: 16px">
          <el-descriptions-item label="作业名">{{ detail.job_name }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ detail.job_type }}</el-descriptions-item>
          <el-descriptions-item label="负责人">{{ detail.owner || '-' }}</el-descriptions-item>
          <el-descriptions-item label="调度">{{ detail.schedule || '-' }}</el-descriptions-item>
          <el-descriptions-item label="描述">{{ detail.description || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-tabs>
          <el-tab-pane :label="`源表 (${detail.source_tables?.length || 0})`">
            <el-table :data="detail.source_tables" border size="small" empty-text="无源表">
              <el-table-column prop="table_name" label="表名" />
              <el-table-column prop="db_name" label="数据库" width="120" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane :label="`目标表 (${detail.target_tables?.length || 0})`">
            <el-table :data="detail.target_tables" border size="small" empty-text="无目标表">
              <el-table-column prop="table_name" label="表名" />
              <el-table-column prop="db_name" label="数据库" width="120" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane :label="`字段映射 (${detail.field_mappings?.length || 0})`">
            <el-table :data="detail.field_mappings" border size="small" empty-text="无字段映射">
              <el-table-column prop="source_table" label="源表" min-width="120" show-overflow-tooltip />
              <el-table-column prop="source_field" label="源字段" min-width="120" show-overflow-tooltip />
              <el-table-column prop="target_table" label="目标表" min-width="120" show-overflow-tooltip />
              <el-table-column prop="target_field" label="目标字段" min-width="120" show-overflow-tooltip />
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
          <el-tab-pane :label="`上下游`">
            <div style="margin-bottom: 12px">
              <strong>上游作业 ({{ detail.upstream?.length || 0 }})</strong>
              <div v-for="u in detail.upstream" :key="u.job_id" style="padding: 4px 0">
                <el-link type="primary" @click="showDetail(u.job_id)">{{ u.job_name }}</el-link>
              </div>
              <div v-if="!detail.upstream?.length" style="color: #999">无</div>
            </div>
            <div>
              <strong>下游作业 ({{ detail.downstream?.length || 0 }})</strong>
              <div v-for="d in detail.downstream" :key="d.job_id" style="padding: 4px 0">
                <el-link type="primary" @click="showDetail(d.job_id)">{{ d.job_name }}</el-link>
              </div>
              <div v-if="!detail.downstream?.length" style="color: #999">无</div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Loading, Refresh, WarnTriangleFilled, FullScreen, Rank } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const store = useAppStore()
const keyword = ref('')
const cycles = ref<any[]>([])
const graphContainer = ref<HTMLElement>()
const drawerVisible = ref(false)
const detail = ref<any>(null)
const detailLoading = ref(false)
let graph: any = null

onMounted(async () => {
  await loadGraph()
  window.addEventListener('resize', onResize)
})

// 工作空间切换时自动刷新
watch(() => store.wsVersion, () => loadGraph())

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  graph?.destroy()
})

// 窗口大小变化时动态调整画布
let resizeTimer: ReturnType<typeof setTimeout> | null = null
function onResize() {
  if (!graph || !graphContainer.value) return
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    const { clientWidth, clientHeight } = graphContainer.value!
    if (clientWidth > 0 && clientHeight > 0) {
      graph.changeSize(clientWidth, clientHeight)
      graph.fitView(30)
    }
  }, 200)
}

async function loadGraph() {
  if (!store.currentWorkspace) return
  const data = await api.get(`/lineage/graph/${store.currentWorkspace.id}`)
  cycles.value = data.cycles || []
  await renderGraph(data.nodes, data.edges)
}

async function renderGraph(nodes: any[], edges: any[]) {
  const G6 = await import('@antv/g6')
  if (graph) {
    graph.destroy()
    graph = null
  }

  // 统一使用 dagre 分层布局：从上到下排列，最小化线交叉
  // dagre 专为 DAG 设计，节点按层级排列，线尽可能不交叉
  graph = new G6.Graph({
    container: graphContainer.value!,
    width: graphContainer.value!.clientWidth,
    height: graphContainer.value!.clientHeight,
    fitView: true,
    fitViewPadding: 40,
    layout: {
      type: 'dagre',
      rankdir: 'TB',          // 从上到下分层排列
      nodesep: 50,            // 同层节点水平间距
      ranksep: 100,           // 层间垂直间距
      align: 'UL',            // 居中对齐，减少线交叉
      controlPoints: false,    // 不用控制点，避免箭头悬空
      preventOverlap: true,
      workerEnabled: false,
    },
    defaultNode: {
      type: 'circle',
      size: 60,
      style: {
        fill: '#e8f0fe',
        stroke: '#1a5fab',
        lineWidth: 2,
      },
      label: '',
      labelCfg: {
        position: 'bottom',
        offset: 8,
        style: {
          fontSize: 12,
          fill: '#333',
          fontWeight: 500,
        },
      },
    },
    defaultEdge: {
      type: 'cubic-vertical',          // 纵向贝塞尔曲线，适合 TB 布局，箭头精确锚定节点边界
      style: {
        endArrow: { path: G6.Arrow.triangle(8, 10, 0), fill: '#90a4ae' },
        stroke: '#90a4ae',
        lineWidth: 1.5,
        lineAppendWidth: 8,            // 增加点击热区
      },
    },
    modes: {
      default: ['drag-canvas', 'zoom-canvas', 'drag-node'],
    },
  })

  // 按作业类型着色
  const typeColors: Record<string, string> = {
    ETL: '#1a5fab',
    PROCEDURE: '#e6a23c',
    SCRIPT: '#909399',
    OTHER: '#909399',
  }

  const g6Nodes = nodes.map((n) => ({
    id: n.id,
    label: n.label,
    job_type: n.job_type,
    style: {
      stroke: typeColors[n.job_type] || '#1a5fab',
      fill: '#fff',
    },
  }))

  const g6Edges = edges.map((e, i) => ({
    source: e.source,
    target: e.target,
    label: '',
    style: { stroke: '#bbb' },
  }))

  graph.data({ nodes: g6Nodes, edges: g6Edges })
  graph.render()

  // 点击节点弹出详情抽屉
  graph.on('node:click', (e: any) => {
    const node = e.item
    const model = node.getModel()
    showDetail(model.id)
  })

  // hover 高亮
  graph.on('node:mouseenter', (e: any) => {
    graph.setItemState(e.item, 'hover', true)
  })
  graph.on('node:mouseleave', (e: any) => {
    graph.setItemState(e.item, 'hover', false)
  })
}

async function showDetail(jobId: string) {
  if (!store.currentWorkspace) return
  drawerVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await api.get(`/jobs/detail/${store.currentWorkspace.id}/${jobId}`)
  } finally {
    detailLoading.value = false
  }
}

function fitView() {
  graph?.fitView(30)
}

function autoLayout() {
  if (!graph) return
  // 重新执行 dagre 分层布局
  graph.updateLayout({
    type: 'dagre',
    rankdir: 'TB',
    nodesep: 50,
    ranksep: 100,
    align: 'UL',
    controlPoints: false,
    preventOverlap: true,
  })
  // 布局完成后自动缩放至适应画布
  setTimeout(() => {
    graph.fitView(30)
  }, 100)
}

async function search() {
  if (!keyword.value || !graph) return
  const allNodes = graph.getNodes()
  allNodes.forEach((n: any) => {
    const model = n.getModel()
    const match = (model.label || '').toLowerCase().includes(keyword.value.toLowerCase())
    graph.updateItem(n, {
      style: { opacity: match ? 1 : 0.15 },
      labelCfg: { style: { opacity: match ? 1 : 0.15 } },
    })
  })
}

async function checkCycles() {
  if (!store.currentWorkspace) return
  const res: any = await api.get(`/lineage/cycles/${store.currentWorkspace.id}`)
  cycles.value = res.cycles
}

function operationTagType(op: string) {
  const map: Record<string, string> = { INSERT: 'success', UPDATE: 'warning', MERGE: 'primary' }
  return map[op?.toUpperCase()] || 'info'
}
</script>

<style scoped>
.graph-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 100px);
}
.graph-container {
  width: 100%;
  flex: 1;
  min-height: 400px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fafafa;
}
</style>
