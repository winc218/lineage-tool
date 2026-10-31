<template>
  <div class="graph-page">
    <div class="toolbar-row">
      <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap">
        <el-input
          v-model="keyword"
          placeholder="搜索作业名"
          style="width: 240px"
          clearable
          @keyup.enter="search"
        />
        <el-button-group>
          <el-button @click="loadGraph" :loading="graphLoading">
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
        <el-alert
          v-if="cycles.length"
          type="error"
          :closable="false"
          show-icon
          style="margin-left: auto; flex: 0 0 auto"
        >
          <template #title>
            <div style="text-align: center">检测到 {{ cycles.length }} 个环路，环路节点和连线已高亮标记</div>
          </template>
        </el-alert>
      </div>
    </div>
    <div ref="graphContainer" class="graph-container" v-loading="graphLoading" />

    <!-- 作业详情抽屉 -->
    <el-drawer v-model="drawerVisible" size="33%" :title="detail?.job_name || '作业详情'">
      <div v-if="detailLoading" style="text-align: center; padding: 40px">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <p>加载中...</p>
      </div>
      <div v-else-if="detail">
        <el-descriptions :column="1" border size="small" style="margin-bottom: 16px">
          <el-descriptions-item label="作业名">{{ detail.job_name }}</el-descriptions-item>
          <el-descriptions-item label="SP名" v-if="detail.sp_name">
            <el-tag type="info">{{ detail.sp_name }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="类型">{{ detail.job_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="负责人">{{ detail.owner || '-' }}</el-descriptions-item>
          <el-descriptions-item label="调度">{{ detail.schedule || '-' }}</el-descriptions-item>
          <el-descriptions-item label="描述">
            <pre style="margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit">{{ detail.description || '-' }}</pre>
          </el-descriptions-item>
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
                <el-link type="primary" @click="jumpToNode(u.job_id)">{{ u.job_name }}</el-link>
              </div>
              <div v-if="!detail.upstream?.length" style="color: #999">无</div>
            </div>
            <div>
              <strong>下游作业 ({{ detail.downstream?.length || 0 }})</strong>
              <div v-for="d in detail.downstream" :key="d.job_id" style="padding: 4px 0">
                <el-link type="primary" @click="jumpToNode(d.job_id)">{{ d.job_name }}</el-link>
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
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
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
const graphLoading = ref(false)
let graph: any = null
let cycleNodeIds = new Set<string>()
let cycleEdgeKeys = new Set<string>()

onMounted(async () => {
  await loadGraph()
  window.addEventListener('resize', onResize)
})

watch(() => store.wsVersion, () => loadGraph())

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  graph?.destroy()
})

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
  graphLoading.value = true
  try {
    const data = await api.get(`/lineage/graph/${store.currentWorkspace.id}`)
    cycles.value = data.cycles || []
    // 提取环路节点和边
    cycleNodeIds = new Set<string>()
    cycleEdgeKeys = new Set<string>()
    for (const cycle of data.cycles || []) {
      for (let i = 0; i < cycle.length; i++) {
        const nodeId = cycle[i].job_id
        cycleNodeIds.add(nodeId)
        const nextId = cycle[(i + 1) % cycle.length].job_id
        cycleEdgeKeys.add(`${nodeId}->${nextId}`)
      }
    }
    await renderGraph(data.nodes, data.edges)
  } finally {
    graphLoading.value = false
  }
}

async function renderGraph(nodes: any[], edges: any[]) {
  const G6 = await import('@antv/g6')
  if (graph) {
    graph.destroy()
    graph = null
  }

  graph = new G6.Graph({
    container: graphContainer.value!,
    width: graphContainer.value!.clientWidth,
    height: graphContainer.value!.clientHeight,
    fitView: true,
    fitViewPadding: 40,
    layout: {
      type: 'dagre',
      rankdir: 'TB',
      nodesep: 50,
      ranksep: 100,
      align: 'UL',
      controlPoints: false,
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
      type: 'cubic-vertical',
      style: {
        endArrow: { path: G6.Arrow.triangle(8, 10, 0), fill: '#90a4ae' },
        stroke: '#90a4ae',
        lineWidth: 1.5,
        lineAppendWidth: 8,
      },
    },
    modes: {
      default: ['drag-canvas', 'zoom-canvas', 'drag-node'],
    },
  })

  const typeColors: Record<string, string> = {
    ETL: '#1a5fab',
    PROCEDURE: '#e6a23c',
    SCRIPT: '#909399',
    OTHER: '#909399',
  }

  const g6Nodes = nodes.map((n) => {
    const isInCycle = cycleNodeIds.has(n.id)
    return {
      id: n.id,
      label: n.label,
      job_type: n.job_type,
      style: {
        stroke: isInCycle ? '#f56c6c' : (typeColors[n.job_type] || '#1a5fab'),
        fill: isInCycle ? '#fef0f0' : '#fff',
        lineWidth: isInCycle ? 3 : 2,
      },
    }
  })

  const g6Edges = edges.map((e) => {
    const edgeKey = `${e.source}->${e.target}`
    const isInCycle = cycleEdgeKeys.has(edgeKey)
    return {
      source: e.source,
      target: e.target,
      label: '',
      style: {
        stroke: isInCycle ? '#f56c6c' : '#bbb',
        lineWidth: isInCycle ? 2.5 : 1.5,
        endArrow: {
          path: G6.Arrow.triangle(8, 10, 0),
          fill: isInCycle ? '#f56c6c' : '#90a4ae',
        },
      },
    }
  })

  graph.data({ nodes: g6Nodes, edges: g6Edges })
  graph.render()

  graph.on('node:click', (e: any) => {
    const node = e.item
    const model = node.getModel()
    showDetail(model.id)
  })

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

async function jumpToNode(jobId: string) {
  // 在血缘图中定位并高亮节点
  if (!graph) return
  const nodeItem = graph.findById(jobId)
  if (nodeItem) {
    // 定位：将节点移到视口中央
    graph.focusItem(nodeItem, true)
    // 高亮该节点（不覆盖环路高亮）
    nodeItem.setState('highlight', true)
    // 点击节点也显示详情
    await showDetail(jobId)
    // 3秒后取消高亮
    setTimeout(() => {
      nodeItem.setState('highlight', false)
    }, 3000)
  } else {
    await showDetail(jobId)
  }
}

function fitView() {
  graph?.fitView(30)
}

function autoLayout() {
  if (!graph) return
  graph.updateLayout({
    type: 'dagre',
    rankdir: 'TB',
    nodesep: 50,
    ranksep: 100,
    align: 'UL',
    controlPoints: false,
    preventOverlap: true,
  })
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
  // 重新加载图以应用高亮
  await loadGraph()
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
