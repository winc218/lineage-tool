<template>
  <el-card>
    <template #header>
      <div style="display: flex; align-items: center; justify-content: space-between">
        <span class="page-title">Mermaid 流程图编辑器</span>
        <div style="display: flex; gap: 8px">
          <el-select v-model="selectedJob" placeholder="选择作业" filterable @change="loadJobMermaid" style="width: 300px">
            <el-option v-for="j in jobs" :key="j.id" :label="j.job_name" :value="j.id" />
          </el-select>
          <el-button @click="newDiagram">新建</el-button>
          <el-button type="primary" @click="saveDiagram">保存</el-button>
          <el-button @click="exportPng" :loading="exporting">导出PNG</el-button>
        </div>
      </div>
    </template>

    <el-row :gutter="16" style="height: calc(100vh - 200px)">
      <el-col :span="12">
        <div class="editor-pane">
          <div class="pane-header">Mermaid 源码</div>
          <el-input
            v-model="mermaidCode"
            type="textarea"
            :rows="20"
            placeholder="输入 Mermaid 流程图语法..."
            class="mermaid-input"
          />
          <div style="margin-top: 8px; color: #909399; font-size: 12px">
            语法参考: <el-link type="primary" href="https://mermaid.js.org/syntax/flowchart.html" target="_blank">Mermaid Flowchart 文档</el-link>
          </div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="editor-pane">
          <div class="pane-header">预览</div>
          <div ref="previewContainer" class="preview-container" v-loading="previewLoading">
            <div v-if="previewError" class="preview-error">
              <el-icon :size="24" color="#f56c6c"><WarnTriangleFilled /></el-icon>
              <p>{{ previewError }}</p>
            </div>
            <div v-else-if="!mermaidCode.trim()" style="color: #999; text-align: center; padding-top: 60px">
              输入 Mermaid 代码即可预览
            </div>
            <div v-else ref="mermaidRender" class="mermaid-render" />
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 已保存的流程图列表 -->
    <el-divider />
    <div class="saved-diagrams">
      <div class="pane-header" style="margin-bottom: 12px">已保存的流程图</div>
      <el-table :data="savedDiagrams" border stripe v-loading="savedLoading" empty-text="暂无保存的流程图">
        <el-table-column prop="job_name" label="作业名" min-width="180" />
        <el-table-column prop="updated_at" label="更新时间" width="180" />
        <el-table-column label="操作" width="180" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="loadDiagram(row)">编辑</el-button>
            <el-button size="small" type="danger" link @click="deleteDiagram(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { WarnTriangleFilled } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const store = useAppStore()
const jobs = ref<any[]>([])
const selectedJob = ref('')
const mermaidCode = ref('')
const previewLoading = ref(false)
const previewError = ref('')
const savedDiagrams = ref<any[]>([])
const savedLoading = ref(false)
const exporting = ref(false)
const mermaidRender = ref<HTMLElement>()
let renderTimer: ReturnType<typeof setTimeout> | null = null

const defaultDiagram = `flowchart TD
    A[源表: t_ods_user] --> B[ETL作业: etl_user_dmt]
    B --> C[目标表: t_dmt_user_summary]
    D[源表: t_ods_order] --> B
    B --> E[目标表: t_dmt_order_stats]
    style B fill:#1a5fab,color:#fff
    style A fill:#e8f0fe
    style C fill:#e8f0fe
    style D fill:#e8f0fe
    style E fill:#e8f0fe`

onMounted(async () => {
  await loadJobs()
  await loadSavedDiagrams()
  mermaidCode.value = defaultDiagram
  renderMermaid()
})

watch(mermaidCode, () => {
  if (renderTimer) clearTimeout(renderTimer)
  renderTimer = setTimeout(renderMermaid, 500)
})

watch(() => store.wsVersion, async () => {
  await loadJobs()
  await loadSavedDiagrams()
})

async function loadJobs() {
  if (!store.currentWorkspace) return
  try {
    jobs.value = await api.get(`/jobs/list/${store.currentWorkspace.id}`)
  } catch { jobs.value = [] }
}

async function loadSavedDiagrams() {
  if (!store.currentWorkspace) return
  savedLoading.value = true
  try {
    savedDiagrams.value = await api.get(`/mermaid/diagrams/${store.currentWorkspace.id}`)
  } catch { savedDiagrams.value = [] }
  finally { savedLoading.value = false }
}

async function loadJobMermaid(jobId: string) {
  if (!store.currentWorkspace) return
  try {
    const res: any = await api.get(`/mermaid/diagrams/${store.currentWorkspace.id}/${jobId}`)
    if (res?.mermaid_text) {
      mermaidCode.value = res.mermaid_text
    } else {
      // 自动生成默认流程图
      const detail: any = await api.get(`/jobs/detail/${store.currentWorkspace.id}/${jobId}`)
      if (detail) {
        mermaidCode.value = generateDefaultDiagram(detail)
      }
    }
  } catch {
    // 无保存的流程图，生成默认
    try {
      const detail: any = await api.get(`/jobs/detail/${store.currentWorkspace.id}/${jobId}`)
      if (detail) {
        mermaidCode.value = generateDefaultDiagram(detail)
      }
    } catch { /* ignore */ }
  }
}

function generateDefaultDiagram(detail: any): string {
  let code = 'flowchart TD\n'
  const srcTables = detail.source_tables || []
  const tgtTables = detail.target_tables || []
  const jobName = detail.job_name || 'Job'

  srcTables.forEach((t: any, i: number) => {
    code += `    S${i + 1}["源表: ${t.table_name}"] --> J["${jobName}"]\n`
    code += `    style S${i + 1} fill:#e8f0fe\n`
  })
  tgtTables.forEach((t: any, i: number) => {
    code += `    J["${jobName}"] --> T${i + 1}["目标表: ${t.table_name}"]\n`
    code += `    style T${i + 1} fill:#e8f0fe\n`
  })
  code += `    style J fill:#1a5fab,color:#fff\n`
  return code
}

async function renderMermaid() {
  if (!mermaidCode.value.trim()) {
    previewError.value = ''
    return
  }
  previewLoading.value = true
  previewError.value = ''
  try {
    const mermaid = (await import('mermaid')).default
    mermaid.initialize({ startOnLoad: false, theme: 'default' })
    await nextTick()
    if (mermaidRender.value) {
      const id = 'mermaid-' + Date.now()
      const { svg } = await mermaid.render(id, mermaidCode.value)
      mermaidRender.value.innerHTML = svg
    }
  } catch (e: any) {
    previewError.value = e.message || '渲染失败'
  } finally {
    previewLoading.value = false
  }
}

async function saveDiagram() {
  if (!store.currentWorkspace || !selectedJob.value) {
    ElMessage.warning('请先选择作业')
    return
  }
  try {
    await api.post(`/mermaid/diagrams/${store.currentWorkspace.id}`, {
      job_id: selectedJob.value,
      mermaid_text: mermaidCode.value,
    })
    ElMessage.success('保存成功')
    await loadSavedDiagrams()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function loadDiagram(row: any) {
  selectedJob.value = row.job_id
  mermaidCode.value = row.mermaid_text || ''
}

async function deleteDiagram(row: any) {
  try {
    await ElMessageBox.confirm('确定删除该流程图吗？', '确认删除', { type: 'warning' })
  } catch { return }
  if (!store.currentWorkspace) return
  try {
    await api.delete(`/mermaid/diagrams/${store.currentWorkspace.id}/${row.job_id}`)
    ElMessage.success('删除成功')
    if (selectedJob.value === row.job_id) {
      mermaidCode.value = defaultDiagram
    }
    await loadSavedDiagrams()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

function newDiagram() {
  mermaidCode.value = defaultDiagram
}

async function exportPng() {
  if (!mermaidRender.value) return
  exporting.value = true
  try {
    const svgElement = mermaidRender.value.querySelector('svg')
    if (!svgElement) {
      ElMessage.warning('请先渲染流程图')
      return
    }
    const svgData = new XMLSerializer().serializeToString(svgElement)
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    const img = new Image()
    img.onload = () => {
      canvas.width = img.width * 2
      canvas.height = img.height * 2
      ctx!.scale(2, 2)
      ctx!.fillStyle = '#ffffff'
      ctx!.fillRect(0, 0, canvas.width, canvas.height)
      ctx!.drawImage(img, 0, 0)
      canvas.toBlob((blob) => {
        const url = URL.createObjectURL(blob!)
        const a = document.createElement('a')
        a.href = url
        a.download = 'mermaid-diagram.png'
        a.click()
        URL.revokeObjectURL(url)
      })
    }
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)))
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.editor-pane {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.pane-header {
  font-weight: bold;
  margin-bottom: 8px;
  color: #303133;
}
.mermaid-input {
  flex: 1;
}
.mermaid-input :deep(textarea) {
  height: 100% !important;
  min-height: 400px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}
.preview-container {
  flex: 1;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: auto;
  min-height: 400px;
  background: #fafafa;
}
.mermaid-render {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100%;
  padding: 16px;
}
.preview-error {
  text-align: center;
  padding: 40px;
  color: #f56c6c;
}
</style>
