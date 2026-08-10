<template>
  <el-card>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
      <h3 style="margin: 0">用户管理</h3>
      <el-button type="primary" @click="openCreate">新建用户</el-button>
    </div>

    <el-table :data="users" border stripe>
      <el-table-column prop="username" label="用户名" width="140" />
      <el-table-column prop="display_name" label="显示名" width="140" />
      <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
      <el-table-column prop="role" label="角色" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="row.role === 'GLOBAL_ADMIN' ? 'danger' : 'info'" size="small">
            {{ row.role === 'GLOBAL_ADMIN' ? '管理员' : '普通用户' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" align="center">
        <template #default="{ row }">
          {{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right" align="center">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="warning" @click="openResetPwd(row)">重置密码</el-button>
          <el-popconfirm
            :title="`确定删除用户 ${row.username}？`"
            @confirm="doDelete(row.id)"
            width="220"
            :disabled="row.username === store.user?.username"
          >
            <template #reference>
              <el-button size="small" type="danger" :disabled="row.username === store.user?.username">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑用户 -->
    <el-dialog v-model="userDialog" :title="editing ? '编辑用户' : '新建用户'" width="480px">
      <el-form label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="userForm.username" :disabled="editing" />
        </el-form-item>
        <el-form-item v-if="!editing" label="密码">
          <el-input v-model="userForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="显示名"><el-input v-model="userForm.display_name" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="userForm.email" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="userForm.role" style="width: 100%">
            <el-option label="普通用户" value="USER" />
            <el-option label="管理员" value="GLOBAL_ADMIN" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doSave">确认</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="resetDialog" title="重置密码" width="400px">
      <p style="margin-bottom: 12px">为用户 <b>{{ resetTarget?.username }}</b> 重置密码：</p>
      <el-input v-model="resetPassword" type="password" show-password placeholder="输入新密码" />
      <template #footer>
        <el-button @click="resetDialog = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="doReset">确认重置</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const store = useAppStore()
const users = ref<any[]>([])

const userDialog = ref(false)
const editing = ref(false)
const saving = ref(false)
const userForm = reactive({ id: '', username: '', password: '', display_name: '', email: '', role: 'USER' })

const resetDialog = ref(false)
const resetTarget = ref<any>(null)
const resetPassword = ref('')
const resetting = ref(false)

async function loadUsers() {
  try {
    users.value = await api.get('/users')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  }
}

function openCreate() {
  editing.value = false
  userForm.id = ''
  userForm.username = ''
  userForm.password = ''
  userForm.display_name = ''
  userForm.email = ''
  userForm.role = 'USER'
  userDialog.value = true
}

function openEdit(row: any) {
  editing.value = true
  userForm.id = row.id
  userForm.username = row.username
  userForm.password = ''
  userForm.display_name = row.display_name
  userForm.email = row.email
  userForm.role = row.role
  userDialog.value = true
}

async function doSave() {
  saving.value = true
  try {
    if (editing.value) {
      await api.put(`/users/${userForm.id}`, {
        display_name: userForm.display_name,
        email: userForm.email,
        role: userForm.role,
      })
      ElMessage.success('修改成功')
    } else {
      if (!userForm.username || !userForm.password) {
        ElMessage.warning('请填写用户名和密码')
        saving.value = false
        return
      }
      await api.post('/users', {
        username: userForm.username,
        password: userForm.password,
        display_name: userForm.display_name,
        email: userForm.email,
        role: userForm.role,
      })
      ElMessage.success('创建成功')
    }
    await loadUsers()
    userDialog.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

function openResetPwd(row: any) {
  resetTarget.value = row
  resetPassword.value = ''
  resetDialog.value = true
}

async function doReset() {
  if (!resetPassword.value || resetPassword.value.length < 6) {
    ElMessage.warning('密码长度不能少于6位')
    return
  }
  resetting.value = true
  try {
    await api.put(`/users/${resetTarget.value.id}/reset-password`, {
      new_password: resetPassword.value,
    })
    ElMessage.success('密码重置成功')
    resetDialog.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '重置失败')
  } finally {
    resetting.value = false
  }
}

async function doDelete(id: string) {
  try {
    await api.delete(`/users/${id}`)
    ElMessage.success('用户已删除')
    await loadUsers()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

onMounted(loadUsers)
</script>
