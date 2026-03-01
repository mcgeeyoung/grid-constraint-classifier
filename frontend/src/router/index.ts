import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import OverviewView from '@/views/OverviewView.vue'
import ImportCongestionView from '@/views/ImportCongestionView.vue'
import ReviewQueueView from '@/views/ReviewQueueView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: DashboardView },
    { path: '/overview', name: 'overview', component: OverviewView },
    { path: '/congestion', name: 'congestion', component: ImportCongestionView },
    { path: '/review', name: 'review', component: ReviewQueueView },
  ],
})

export default router
