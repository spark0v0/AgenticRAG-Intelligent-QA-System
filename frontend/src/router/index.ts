import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    {
      path: '/chat',
      component: () => import('../views/ChatView.vue'),
      meta: { title: '智能问答' },
    },
    {
      path: '/tools',
      component: () => import('../views/ToolsView.vue'),
      meta: { title: '工具中心' },
    },
    {
      path: '/providers',
      component: () => import('../views/ProvidersView.vue'),
      meta: { title: '模型供应商' },
    },
    {
      path: '/runs',
      component: () => import('../views/RunsView.vue'),
      meta: { title: '运行分析' },
    },
    {
      path: '/system',
      component: () => import('../views/SystemView.vue'),
      meta: { title: '系统概览' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/chat' },
  ],
})
