import axios from 'axios'
import { ElMessage, ElNotification } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
      return Promise.reject(err)
    }
    // 详细错误信息展示
    const detail = err.response?.data?.detail
    const status = err.response?.status
    if (detail) {
      const detailStr = typeof detail === 'string' ? detail : JSON.stringify(detail)
      // 长错误信息用 Notification 展示
      if (detailStr.length > 50) {
        ElNotification({
          title: `请求失败 (${status || '网络错误'})`,
          message: detailStr,
          type: 'error',
          duration: 8000,
        })
      } else {
        ElMessage.error(detailStr)
      }
    } else if (err.code === 'ECONNABORTED') {
      ElMessage.error('请求超时，请稍后重试')
    } else if (!err.response) {
      ElMessage.error('网络连接失败，请检查服务是否正常运行')
    } else {
      ElMessage.error(`服务器错误 (${status})，请查看日志`)
    }
    return Promise.reject(err)
  }
)

export default api
