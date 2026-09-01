import { createRouter, createWebHistory } from 'vue-router'
import Home from '@/views/Home.vue'
import SubsystemView from '@/views/SubsystemView.vue'
import NodeView from '@/views/NodeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: Home },
    { path: '/:subsystem', name: 'subsystem', component: SubsystemView, props: true },
    { path: '/:subsystem/:name/:mode?/:version?', name: 'node', component: NodeView, props: true },
  ],
})

export default router
