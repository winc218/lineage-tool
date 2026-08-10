<template>
  <el-container style="height: 100vh">
    <el-header style="background: #1a5fab; color: white; display: flex; align-items: center; gap: 12px; height: 56px; padding: 0 20px">
      <span style="font-weight: bold; font-size: 16px; white-space: nowrap">血缘分析工具</span>
      <el-select
        v-model="wsId"
        placeholder="选择工作空间"
        style="width: 200px"
        @change="onWsChange"
      >
        <el-option
          v-for="w in store.workspaces"
          :key="w.id"
          :label="`${w.name} (${w.role})`"
          :value="w.id"
        />
      </el-select>
      <el-menu
        :default-active="route.name as string"
        mode="horizontal"
        background-color="#1a5fab"
        text-color="white"
        active-text-color="#ffd04b"
        router
        style="flex: 1; border: none"
      >
        <el-menu-item index="dashboard" :route="{ name: 'dashboard' }">仪表盘</el-menu-item>
        <el-menu-item index="import" :route="{ name: 'import' }">导入</el-menu-item>
        <el-menu-item index="graph" :route="{ name: 'graph' }">血缘图</el-menu-item>
        <el-menu-item index="jobs" :route="{ name: 'jobs' }">作业管理</el-menu-item>
        <el-menu-item index="sp" :route="{ name: 'sp' }">SP校验</el-menu-item>
        <el-menu-item index="workspace" :route="{ name: 'workspace' }">工作空间</el-menu-item>
        <el-menu-item v-if="isAdmin" index="users" :route="{ name: 'users' }">用户管理</el-menu-item>
      </el-menu>
      <!-- 用户区域：头像 + 用户名 + 下拉菜单 -->
      <el-dropdown @command="onCommand" trigger="click">
        <div style="display: flex; align-items: center; gap: 8px; cursor: pointer">
          <div class="user-avatar">
            {{ (store.user?.display_name || store.user?.username || '?').charAt(0).toUpperCase() }}
          </div>
          <div style="display: flex; flex-direction: column; line-height: 1.2; color: white">
            <span style="font-size: 13px">{{ store.user?.display_name || store.user?.username }}</span>
            <span style="font-size: 11px; opacity: 0.7">{{ roleLabel }}</span>
          </div>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              <span style="color: #999">{{ store.user?.username }}</span>
            </el-dropdown-item>
            <el-dropdown-item divided command="change-password">
              <el-icon><Key /></el-icon> 修改密码
            </el-dropdown-item>
            <el-dropdown-item command="workspace">
              <el-icon><Setting /></el-icon> 工作空间管理
            </el-dropdown-item>
            <el-dropdown-item command="logout" divided>
              <el-icon><SwitchButton /></el-icon> 退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </el-header>
    <el-main>
      <router-view v-if="store.currentWorkspace || route.name === 'users' || route.name === 'workspace'" />
      <div v-else style="text-align: center; padding: 80px">
        <p style="color: #909399">请先选择或创建工作空间</p>
        <el-button type="primary" @click="$router.push('/workspace')">去创建</el-button>
      </div>
    </el-main>

    <!-- 修改密码对话框 -->
    <el-dialog v-model="pwdDialog" title="修改密码" width="400px">
      <el-form label-width="80px">
        <el-form-item label="旧密码">
          <el-input v-model="pwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="pwdForm.confirm_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdDialog = false">取消</el-button>
        <el-button type="primary" :loading="pwdLoading" @click="doChangePassword">确认</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Setting, SwitchButton, Key } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import api from '@/api'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const wsId = ref(store.currentWorkspace?.id || '')

const isAdmin = computed(() => store.user?.role === 'GLOBAL_ADMIN')

const roleLabel = computed(() => {
  const r = store.currentWorkspace?.role
  if (r === 'OWNER') return '所有者'
  if (r === 'EDITOR') return '编辑者'
  if (r === 'VIEWER') return '只读'
  return store.user?.role === 'GLOBAL_ADMIN' ? '系统管理员' : ''
})

// 启动时恢复会话
onMounted(async () => {
  if (!store.user) {
    await store.restoreSession()
  }
  wsId.value = store.currentWorkspace?.id || ''
})

watch(
  () => store.currentWorkspace,
  (ws) => { wsId.value = ws?.id || '' }
)

function onWsChange(id: string) {
  store.setWorkspace(id)
}

function onCommand(cmd: string) {
  if (cmd === 'logout') {
    store.logout()
    router.push('/login')
  } else if (cmd === 'workspace') {
    router.push('/workspace')
  } else if (cmd === 'change-password') {
    pwdDialog.value = true
  }
}

// 修改密码
const pwdDialog = ref(false)
const pwdLoading = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })

async function doChangePassword() {
  if (!pwdForm.old_password || !pwdForm.new_password) {
    ElMessage.warning('请填写完整')
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  pwdLoading.value = true
  try {
    await api.put('/auth/change-password', {
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password,
    })
    ElMessage.success('密码修改成功')
    pwdDialog.value = false
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '修改失败')
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: bold;
  color: white;
  border: 2px solid rgba(255, 255, 255, 0.4);
}
</style>
