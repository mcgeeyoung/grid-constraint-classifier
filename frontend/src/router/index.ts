import { createRouter, createWebHistory } from 'vue-router'
import ExplorerView from '@/views/ExplorerView.vue'
import ReviewQueueView from '@/views/ReviewQueueView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'explorer', component: ExplorerView },
    { path: '/review', name: 'review', component: ReviewQueueView },
  ],
})

export default router
