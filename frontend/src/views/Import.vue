<template>
  <el-card>
    <el-steps :active="step" finish-status="success" align-center>
      <el-step title="选择文件" />
      <el-step title="确认列映射" />
      <el-step title="预览校验" />
      <el-step title="确认导入" />
    </el-steps>

    <!-- Step 0: 选文件 -->
    <div v-if="step === 0" class="step-content">
      <div class="upload-area">
        <el-upload :auto-upload="true" :show-file-list="false" :http-request="onUpload" drag>
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">将 Excel 文件拖到此处，或<em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">仅支持 .xlsx / .xls 格式</div>
          </template>
        </el-upload>
      </div>
      <div v-if="parseResult" class="parse-result">
        <el-alert type="success" :closable="false" show-icon>
          <template #title>
            解析成功：共 {{ parseResult.count }} 行，Sheet 列表：{{ parseResult.sheets.join(', ') }}
          </template>
        </el-alert>
        <div style="margin-top: 16px; text-align: center">
          <el-button type="primary" @click="step = 1">下一步</el-button>
        </div>
      </div>
    </div>

    <!-- Step 1: 确认列映射 -->
    <div v-if="step === 1" class="step-content">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
        <template #title>
          系统已自动匹配列名，请确认映射。必填字段：作业名、作业类型、源表、目标表、存过名称。
        </template>
      </el-alert>
      <el-table :data="mappingRows" border size="small">
        <el-table-column label="Excel 列名" prop="excelCol" width="200" />
        <el-table-column label="映射到系统字段">
          <template #default="{ row }">
            <el-select v-model="row.sysField" placeholder="不映射" clearable style="width: 100%" filterable>
              <el-option-group label="必填字段">
                <el-option
                  v-for="f in requiredFields"
                  :key="f"
                  :label="fieldLabel(f)"
                  :value="f"
                  :disabled="isFieldUsed(f, row)"
                />
              </el-option-group>
              <el-option-group label="可选字段">
                <el-option
                  v-for="f in optionalFields"
                  :key="f"
                  :label="fieldLabel(f)"
                  :value="f"
                  :disabled="isFieldUsed(f, row)"
                />
              </el-option-group>
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="自动匹配" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.autoMatched" type="success" size="small">已匹配</el-tag>
            <span v-else style="color: #ccc">-</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="step-actions">
        <el-button @click="step = 0">上一步</el-button>
        <el-button type="primary" @click="doValidate">校验</el-button>
      </div>
    </div>

    <!-- Step 2: 预览 -->
    <div v-if="step === 2" class="step-content">
      <el-alert v-if="validateResult.errors.length" type="warning" :closable="false" show-icon style="margin-bottom: 16px">
        共 {{ validateResult.errors.length }} 条错误
      </el-alert>
      <el-table :data="validateResult.preview.slice(0, 50)" border size="small" max-height="450">
        <el-table-column
          v-for="f in previewFields"
          :key="f"
          :label="fieldLabel(f)"
          :prop="f"
          min-width="120"
          show-overflow-tooltip
        />
      </el-table>
      <div class="step-summary">
        <span>有效数据 <b style="color: #67c23a">{{ validateResult.total_valid }}</b> 条，无效 <b style="color: #f56c6c">{{ validateResult.total_invalid }}</b> 条</span>
      </div>
      <div class="step-actions">
        <el-button @click="step = 1">上一步</el-button>
        <el-button type="primary" @click="doImport" :disabled="validateResult.total_valid === 0">确认导入</el-button>
      </div>
    </div>

    <!-- Step 3: 完成 -->
    <div v-if="step === 3" class="step-content">
      <el-result icon="success" title="导入成功" :sub-title="`批次号: ${importResult.batch_no}，共 ${importResult.job_count} 个作业`">
        <template #extra>
          <el-button type="primary" @click="$router.push('/graph')">查看血缘图</el-button>
          <el-button @click="step = 0">继续导入</el-button>
        </template>
      </el-result>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const store = useAppStore()
const step = ref(0)
const fileData = ref<File | null>(null)
const parseResult = ref<any>(null)
const sysFields = ref<string[]>([])
const requiredFields = ref<string[]>([])
const mappingRows = ref<{ excelCol: string; sysField: string; autoMatched: boolean }[]>([])
const validateResult = reactive<any>({ errors: [], preview: [], total_valid: 0, total_invalid: 0 })
const importResult = ref<any>({})

const FIELD_LABELS: Record<string, string> = {
  job_name: '作业名',
  job_type: '作业类型',
  source_tables: '源表',
  target_tables: '目标表',
  sp_name: '存过名称',
  field_mappings: '字段映射',
  schedule: '调度',
  description: '描述',
}

const optionalFields = computed(() => sysFields.value.filter(f => !requiredFields.value.includes(f)))

const previewFields = computed(() => {
  if (!validateResult.preview.length) return sysFields.value
  return sysFields.value.filter(f => validateResult.preview.some((r: any) => r[f] !== undefined && r[f] !== ''))
})

function fieldLabel(f: string) {
  return FIELD_LABELS[f] || f
}

function isFieldUsed(field: string, currentRow: any) {
  return mappingRows.value.some(r => r !== currentRow && r.sysField === field)
}

async function onUpload(req: any) {
  fileData.value = req.file
  const fd = new FormData()
  fd.append('file', req.file)
  try {
    const res: any = await api.post('/import/parse', fd)
    parseResult.value = res
    const fieldsRes: any = await api.get('/import/fields')
    sysFields.value = fieldsRes.fields
    requiredFields.value = fieldsRes.required
    // 使用后端返回的自动匹配结果
    const autoMapping = res.auto_mapping || {}
    mappingRows.value = res.headers.map((h: string) => ({
      excelCol: h,
      sysField: autoMapping[h] || '',
      autoMatched: !!autoMapping[h],
    }))
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '解析失败')
  }
}

function buildMapping(): Record<string, string> {
  const m: Record<string, string> = {}
  for (const r of mappingRows.value) {
    if (r.sysField) m[r.excelCol] = r.sysField
  }
  return m
}

async function doValidate() {
  if (!fileData.value) return
  const mapped = new Set(Object.values(buildMapping()))
  const missing = requiredFields.value.filter(f => !mapped.has(f))
  if (missing.length) {
    ElMessage.warning(`必填字段未映射: ${missing.map(fieldLabel).join(', ')}`)
    return
  }
  const fd = new FormData()
  fd.append('file', fileData.value)
  fd.append('mapping', JSON.stringify(buildMapping()))
  try {
    const res: any = await api.post('/import/validate', fd)
    Object.assign(validateResult, res)
    step.value = 2
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '校验失败')
  }
}

async function doImport() {
  if (!fileData.value || !store.currentWorkspace) return
  const fd = new FormData()
  fd.append('file', fileData.value)
  fd.append('mapping', JSON.stringify(buildMapping()))
  try {
    importResult.value = await api.post(`/import/confirm/${store.currentWorkspace.id}`, fd)
    step.value = 3
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  }
}
</script>

<style scoped>
.step-content {
  margin-top: 24px;
  min-height: 300px;
}
.upload-area {
  max-width: 500px;
  margin: 20px auto;
}
.parse-result {
  max-width: 500px;
  margin: 20px auto;
}
.step-actions {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  gap: 12px;
}
.step-summary {
  margin-top: 16px;
  text-align: center;
  color: #606266;
  font-size: 14px;
}
</style>
