<template>
  <el-card>
    <el-steps :active="step" finish-status="success" align-center>
      <el-step title="关联SP来源" />
      <el-step title="拉取并匹配" />
      <el-step title="解析与比对" />
      <el-step title="补充血缘" />
      <el-step title="采纳修订" />
    </el-steps>

    <!-- Step 0: 关联来源 -->
    <div v-if="step === 0" class="step-content">
      <el-form label-width="120px" class="sp-form">
        <el-form-item label="来源名称">
          <el-input v-model="source.name" placeholder="请输入来源名称" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="source.type">
            <el-radio value="git">Git 仓库</el-radio>
            <el-radio value="database">数据库</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="source.type === 'git'">
          <el-form-item label="协议">
            <el-radio-group v-model="source.config.git_protocol">
              <el-radio value="https">HTTPS (账号密码)</el-radio>
              <el-radio value="ssh">Git (SSH密钥)</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="仓库URL">
            <el-input v-model="source.config.url" :placeholder="source.config.git_protocol === 'ssh' ? 'git@git.example.com:repo.git' : 'https://git.example.com/repo.git'" />
          </el-form-item>
          <el-form-item label="分支">
            <el-input v-model="source.config.branch" placeholder="main" />
          </el-form-item>
          <template v-if="source.config.git_protocol === 'https'">
            <el-form-item label="账号">
              <el-input v-model="source.config.username" placeholder="Git账号" />
            </el-form-item>
            <el-form-item label="密码/Token">
              <el-input v-model="source.config.token" placeholder="访问令牌或个人密码" show-password />
            </el-form-item>
          </template>
          <template v-else>
            <el-form-item label="SSH密钥">
              <el-input v-model="source.config.ssh_key" type="textarea" :rows="4" placeholder="粘贴SSH私钥内容" />
            </el-form-item>
          </template>
          <el-form-item label="SP目录">
            <el-input v-model="source.config.sp_dir" placeholder="/" />
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="连接串">
            <el-input v-model="source.config.conn_str" placeholder="mssql+pymssql://user:pass@host:1433/db" />
          </el-form-item>
          <el-form-item label="Schema">
            <el-input v-model="source.config.schema" placeholder="dbo" />
          </el-form-item>
        </template>
        <el-form-item>
          <el-button type="primary" @click="createAndPull">创建并拉取</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- Step 1: 匹配结果 -->
    <div v-if="step === 1" class="step-content">
      <el-result icon="info" title="匹配完成" :sub-title="`自动匹配 ${matchResult.matched}，疑似 ${matchResult.fuzzy}，未匹配 ${matchResult.unmatched}`">
        <template #extra>
          <el-button type="primary" @click="doParse">解析 SP</el-button>
        </template>
      </el-result>
    </div>

    <!-- Step 2: 解析结果 -->
    <div v-if="step === 2" class="step-content">
      <el-result icon="info" title="解析完成" :sub-title="`成功 ${parseResult.success}，失败 ${parseResult.failed}`">
        <template #extra>
          <el-button type="primary" @click="doReconcile">执行血缘比对</el-button>
        </template>
      </el-result>
    </div>

    <!-- Step 3: 补充血缘 -->
    <div v-if="step === 3" class="step-content">
      <el-result icon="info" title="血缘比对完成" :sub-title="`发现 ${diffs.length} 条差异`">
        <template #extra>
          <el-button type="primary" @click="doSupplement">自动补充字段血缘</el-button>
          <el-button @click="step = 4">跳过，直接查看差异</el-button>
        </template>
      </el-result>
    </div>

    <!-- Step 4: 差异采纳 -->
    <div v-if="step === 4" class="step-content">
      <div class="step-actions" style="justify-content: flex-end; margin-bottom: 16px">
        <el-button type="primary" @click="applyPatch" :disabled="selected.length === 0">
          采纳选中 ({{ selected.length }})
        </el-button>
      </div>
      <el-table :data="diffs" border @selection-change="onSel" size="small">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="diff_type" label="类型" width="120" align="center" />
        <el-table-column prop="excel_value" label="Excel登记" min-width="200" show-overflow-tooltip />
        <el-table-column prop="sp_value" label="SP解析" min-width="200" show-overflow-tooltip />
        <el-table-column prop="action" label="建议" width="80" align="center" />
      </el-table>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const store = useAppStore()
const step = ref(0)
const sourceId = ref('')
const source = reactive({
  name: '',
  type: 'git',
  config: {} as Record<string, string>,
})
const matchResult = ref<any>({})
const parseResult = ref<any>({})
const diffs = ref<any[]>([])
const selected = ref<string[]>([])

async function createAndPull() {
  if (!store.currentWorkspace || !source.name) {
    ElMessage.warning('请填写来源名称')
    return
  }
  try {
    const res: any = await api.post(`/sp/sources/${store.currentWorkspace.id}`, {
      name: source.name,
      type: source.type,
      config: source.config,
    })
    sourceId.value = res.id
    await api.post(`/sp/sources/${store.currentWorkspace.id}/${sourceId.value}/pull`)
    matchResult.value = await api.post(`/sp/sources/${store.currentWorkspace.id}/${sourceId.value}/match`)
    step.value = 1
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

async function doParse() {
  if (!store.currentWorkspace) return
  try {
    parseResult.value = await api.post(`/sp/sources/${store.currentWorkspace.id}/${sourceId.value}/parse`)
    step.value = 2
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '解析失败')
  }
}

async function doReconcile() {
  if (!store.currentWorkspace) return
  try {
    await api.post(`/sp/sources/${store.currentWorkspace.id}/${sourceId.value}/reconcile`)
    diffs.value = await api.get(`/sp/diffs/${store.currentWorkspace.id}`)
    step.value = 3
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '比对失败')
  }
}

async function doSupplement() {
  if (!store.currentWorkspace) return
  try {
    const res: any = await api.post(`/sp/sources/${store.currentWorkspace.id}/${sourceId.value}/supplement`)
    ElMessage.success(`已补充 ${res.added} 条字段血缘，跳过 ${res.skipped} 条已存在的`)
    diffs.value = await api.get(`/sp/diffs/${store.currentWorkspace.id}`)
    step.value = 4
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '补充失败')
  }
}

function onSel(rows: any[]) {
  selected.value = rows.map((r) => r.id)
}

async function applyPatch() {
  if (!store.currentWorkspace) return
  try {
    const res: any = await api.post(`/sp/diffs/${store.currentWorkspace.id}/apply`, { diff_ids: selected.value })
    ElMessage.success(`已采纳 ${res.accepted} 项修订`)
    diffs.value = await api.get(`/sp/diffs/${store.currentWorkspace.id}`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '采纳失败')
  }
}
</script>

<style scoped>
.step-content {
  margin-top: 24px;
  min-height: 300px;
}
.sp-form {
  max-width: 600px;
}
.step-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
