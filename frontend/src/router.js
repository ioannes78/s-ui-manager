import { createRouter, createWebHashHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('./views/DashboardView.vue'), meta: { title: '运行概览' } },
    { path: '/nodes', name: 'nodes', component: () => import('./views/NodesView.vue'), meta: { title: '节点管理' } },
    { path: '/users', name: 'users', component: () => import('./views/UsersView.vue'), meta: { title: '中央用户' } },
    { path: '/tasks', name: 'tasks', component: () => import('./views/TasksView.vue'), meta: { title: '任务中心' } },
    { path: '/alerts', name: 'alerts', component: () => import('./views/AlertsView.vue'), meta: { title: '监控告警' } },
    { path: '/audit', name: 'audit', component: () => import('./views/AuditView.vue'), meta: { title: '审计日志' } },
  ],
})
