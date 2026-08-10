<template>
  <div class="login-container">
    <el-card class="login-card" shadow="always">
      <div class="login-header">
        <div class="login-logo">LT</div>
        <h2>批量作业数据血缘关系分析与管理工具</h2>
      </div>
      <el-form @submit.prevent="handleLogin" label-position="top" :model="form" class="login-form">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" size="large" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" size="large" />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" size="large" style="width: 100%; margin-top: 8px">
          登 录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const store = useAppStore()
const loading = ref(false)
const form = reactive({ username: 'admin', password: 'admin123' })

async function handleLogin() {
  loading.value = true
  try {
    await store.login(form.username, form.password)
    router.push('/')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #1a5fab 0%, #2c7ec7 100%);
}
.login-card {
  width: 420px;
  border-radius: 12px;
}
.login-header {
  text-align: center;
  margin-bottom: 28px;
}
.login-logo {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: #1a5fab;
  color: white;
  font-size: 22px;
  font-weight: bold;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
}
.login-card h2 {
  text-align: center;
  color: #303133;
  font-size: 17px;
  margin: 0;
  line-height: 1.5;
}
.login-form {
  margin-top: 8px;
}
.login-form :deep(.el-form-item) {
  margin-bottom: 18px;
}
.login-form :deep(.el-form-item__label) {
  font-weight: 500;
  padding-bottom: 4px;
}
</style>
