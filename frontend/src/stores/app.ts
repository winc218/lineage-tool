import { defineStore } from 'pinia'
import api from '@/api'

interface User {
  id: string
  username: string
  display_name: string
  role: string
}

interface Workspace {
  id: string
  name: string
  description: string
  db_mode: string
  role: string
  owner_name: string
}

export const useAppStore = defineStore('app', {
  state: () => ({
    user: null as User | null,
    workspaces: [] as Workspace[],
    currentWorkspace: null as Workspace | null,
    /** 工作空间切换计数器，各页面 watch 此值实现自动刷新 */
    wsVersion: 0,
  }),
  actions: {
    async login(username: string, password: string) {
      const res: any = await api.post('/auth/login', `username=${username}&password=${password}`, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      localStorage.setItem('token', res.access_token)
      this.user = res.user
      await this.fetchWorkspaces()
    },

    /** 页面刷新后恢复登录态（token 存在但 user 丢失时调用） */
    async restoreSession() {
      const token = localStorage.getItem('token')
      if (!token) return false
      try {
        const me: any = await api.get('/auth/me')
        this.user = me
        await this.fetchWorkspaces()
        // 恢复上次选中的工作空间
        const savedWsId = localStorage.getItem('wsId')
        if (savedWsId && this.workspaces.length) {
          const ws = this.workspaces.find((w) => w.id === savedWsId)
          if (ws) {
            this.currentWorkspace = ws
          }
        }
        return true
      } catch {
        this.logout()
        return false
      }
    },

    async fetchWorkspaces() {
      this.workspaces = await api.get('/workspaces')
      if (this.workspaces.length && !this.currentWorkspace) {
        this.currentWorkspace = this.workspaces[0]
        localStorage.setItem('wsId', this.currentWorkspace.id)
      }
    },

    /** 切换工作空间，触发 wsVersion +1 通知所有页面刷新 */
    setWorkspace(id: string) {
      this.currentWorkspace = this.workspaces.find((w) => w.id === id) || null
      if (this.currentWorkspace) {
        localStorage.setItem('wsId', this.currentWorkspace.id)
        this.wsVersion++
      }
    },

    logout() {
      localStorage.removeItem('token')
      localStorage.removeItem('wsId')
      this.user = null
      this.workspaces = []
      this.currentWorkspace = null
      this.wsVersion++
    },
  },
})
