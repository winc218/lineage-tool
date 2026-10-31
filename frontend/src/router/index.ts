import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue') },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    children: [
      { path: '', name: 'dashboard', component: () => import('@/views/Dashboard.vue') },
      { path: 'import', name: 'import', component: () => import('@/views/Import.vue') },
      { path: 'graph', name: 'graph', component: () => import('@/views/Graph.vue') },
      { path: 'jobs', name: 'jobs', component: () => import('@/views/Jobs.vue') },
      { path: 'sp', name: 'sp', component: () => import('@/views/SPReconcile.vue') },
      { path: 'workspace', name: 'workspace', component: () => import('@/views/Workspace.vue') },
      { path: 'users', name: 'users', component: () => import('@/views/UserManage.vue') },
      { path: 'db-admin', name: 'db-admin', component: () => import('@/views/DBAdmin.vue') },
      { path: 'mermaid', name: 'mermaid', component: () => import('@/views/MermaidEditor.vue') },
    ],
  },
  // 404 fallback 重定向到首页
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (!token && to.name !== 'login') {
    next({ name: 'login' })
  } else {
    next()
  }
})

export default router
