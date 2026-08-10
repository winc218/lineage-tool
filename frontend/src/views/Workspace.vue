<template>
  <el-card>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
      <h3 style="margin: 0">工作空间管理</h3>
      <div>
        <el-tag v-if="isAdmin" type="danger" style="margin-right: 8px">管理员模式</el-tag>
        <el-tag v-else type="info" style="margin-right: 8px">只读模式</el-tag>
        <el-button v-if="isAdmin" type="primary" @click="openCreate">新建工作空间</el-button>
      </div>
    </div>

    <el-table :data="store.workspaces" border>
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="role" label="我的角色" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="roleTagType(row.role)" size="small">{{ roleLabel(row.role) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="owner_name" label="所有者" width="100" align="center" />
      <el-table-column v-if="isAdmin" label="操作" width="220" fixed="right" align="center">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" @click="openMembers(row)">成员</el-button>
          <el-popconfirm title="确定删除此工作空间？删除后不可恢复" @confirm="doDelete(row.id)" width="220">
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑工作空间 -->
    <el-dialog v-model="wsDialog" :title="editing ? '编辑工作空间' : '新建工作空间'" width="480px">
      <el-form label-width="80px">
        <el-form-item label="名称"><el-input v-model="wsForm.name" placeholder="请输入工作空间名称" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="wsForm.description" type="textarea" :rows="3" placeholder="可选" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="wsDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doSave">确认</el-button>
      </template>
    </el-dialog>

    <!-- 成员管理 -->
    <el-dialog v-model="memberDialog" title="成员管理" width="640px">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
        <span style="font-weight: bold">{{ currentWs?.name }} - 成员列表</span>
        <el-button type="primary" size="small" @click="memberAddDialog = true">添加成员</el-button>
      </div>
      <el-table :data="members" border size="small">
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="display_name" label="显示名" />
        <el-table-column prop="role" label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role)">{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <template v-if="row.role !== 'OWNER'">
              <el-select
                :model-value="row.role"
                size="small"
                style="width: 100px; margin-right: 8px"
                @change="(val: string) => doUpdateMember(row, val)"
              >
                <el-option label="编辑者" value="EDITOR" />
                <el-option label="只读" value="VIEWER" />
              </el-select>
              <el-popconfirm title="确定移除？" @confirm="doRemoveMember(row.id)" width="200">
                <template #reference>
                  <el-button size="small" type="danger">移除</el-button>
                </template>
              </el-popconfirm>
            </template>
            <span v-else style="color: #999">所有者</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 添加成员 -->
    <el-dialog v-model="memberAddDialog" title="添加成员" width="460px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="用户">
          <el-select v-model="memberForm.user_id" filterable placeholder="搜索用户名" style="width: 100%">
            <el-option
              v-for="u in allUsers.filter(u => !members.some(m => m.user_id === u.id))"
              :key="u.id"
              :label="`${u.username} (${u.display_name || '-'})`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="memberForm.role" style="width: 100%">
            <el-option label="编辑者" value="EDITOR" />
            <el-option label="只读" value="VIEWER" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="memberAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="memberSaving" @click="doAddMember">添加</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const store = useAppStore()
const isAdmin = computed(() => store.user?.role === 'GLOBAL_ADMIN')

// 工作空间 CRUD
const wsDialog = ref(false)
const editing = ref(false)
const saving = ref(false)
const wsForm = reactive({ id: '', name: '', description: '' })

function openCreate() {
  editing.value = false
  wsForm.id = ''
  wsForm.name = ''
  wsForm.description = ''
  wsDialog.value = true
}

function openEdit(row: any) {
  editing.value = true
  wsForm.id = row.id
  wsForm.name = row.name
  wsForm.description = row.description
  wsDialog.value = true
}

async function doSave() {
  if (!wsForm.name) {
    ElMessage.warning('请输入名称')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await api.put(`/workspaces/${wsForm.id}`, {
        name: wsForm.name,
        description: wsForm.description,
      })
      ElMessage.success('修改成功')
    } else {
      await api.post('/workspaces', {
        name: wsForm.name,
        description: wsForm.description,
      })
      ElMessage.success('创建成功')
    }
    await store.fetchWorkspaces()
    wsDialog.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

async function doDelete(id: string) {
  try {
    await api.delete(`/workspaces/${id}`)
    ElMessage.success('删除成功')
    await store.fetchWorkspaces()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// 成员管理
const memberDialog = ref(false)
const currentWs = ref<any>(null)
const members = ref<any[]>([])
const allUsers = ref<any[]>([])
const memberAddDialog = ref(false)
const memberSaving = ref(false)
const memberForm = reactive({ user_id: '', role: 'VIEWER' })

async function openMembers(row: any) {
  currentWs.value = row
  memberDialog.value = true
  await loadMembers(row.id)
  await loadAllUsers()
}

async function loadMembers(wsId: string) {
  try {
    members.value = await api.get(`/workspaces/${wsId}/members`)
  } catch (e: any) {
    ElMessage.error('加载成员失败')
  }
}

async function loadAllUsers() {
  try {
    allUsers.value = await api.get('/users')
  } catch {
    allUsers.value = []
  }
}

async function doAddMember() {
  if (!memberForm.user_id) {
    ElMessage.warning('请选择用户')
    return
  }
  memberSaving.value = true
  try {
    await api.post(`/workspaces/${currentWs.value.id}/members`, {
      user_id: memberForm.user_id,
      role: memberForm.role,
    })
    ElMessage.success('添加成功')
    memberForm.user_id = ''
    memberForm.role = 'VIEWER'
    memberAddDialog.value = false
    await loadMembers(currentWs.value.id)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  } finally {
    memberSaving.value = false
  }
}

async function doUpdateMember(row: any, role: string) {
  try {
    await api.put(`/workspaces/${currentWs.value.id}/members/${row.id}?role=${role}`)
    ElMessage.success('角色已更新')
    await loadMembers(currentWs.value.id)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '修改失败')
  }
}

async function doRemoveMember(memberId: string) {
  try {
    await api.delete(`/workspaces/${currentWs.value.id}/members/${memberId}`)
    ElMessage.success('已移除')
    await loadMembers(currentWs.value.id)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '移除失败')
  }
}

// 角色显示
function roleLabel(role: string) {
  if (role === 'OWNER') return '所有者'
  if (role === 'EDITOR') return '编辑者'
  if (role === 'VIEWER') return '只读'
  return role
}

function roleTagType(role: string) {
  if (role === 'OWNER') return 'danger'
  if (role === 'EDITOR') return 'warning'
  return 'info'
}

onMounted(async () => {
  await store.fetchWorkspaces()
})
</script>
