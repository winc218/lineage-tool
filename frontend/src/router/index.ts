import { createRouter, createWebHistory } from 'vue-router'

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
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
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
