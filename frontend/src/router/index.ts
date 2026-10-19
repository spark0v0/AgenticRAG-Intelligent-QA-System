import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, _from, saved) {
    if (saved) return saved
    if (to.hash)
      return {
        el: to.hash,
        top: 96,
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      }
    return to.meta.layout === 'home' ? { top: 0 } : false
  },
  routes: [
    {
      path: '/',
      component: () => import('../views/HomeView.vue'),
      meta: { title: '让答案有据可循', layout: 'home' },
    },
    {
      path: '/',
      component: () => import('../layouts/WorkbenchLayout.vue'),
      meta: { layout: 'workbench' },
      children: [
        {
          path: 'chat',
          component: () => import('../views/ChatView.vue'),
          meta: { title: '智能问答' },
        },
        {
          path: 'knowledge',
          component: () => import('../views/KnowledgeView.vue'),
          meta: { title: '知识库' },
        },
        {
          path: 'tools',
          component: () => import('../views/ToolsView.vue'),
          meta: { title: '工具中心' },
        },
        {
          path: 'providers',
          component: () => import('../views/ProvidersView.vue'),
          meta: { title: '模型供应商' },
        },
        {
          path: 'runs',
          component: () => import('../views/RunsView.vue'),
          meta: { title: '运行分析' },
        },
        {
          path: 'system',
          component: () => import('../views/SystemView.vue'),
          meta: { title: '系统概览' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/chat' },
  ],
})
