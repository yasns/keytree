import { createRouter, createWebHistory } from 'vue-router'
import Home from '@/views/Home.vue'
import NodeView from '@/views/NodeView.vue'
import NotFoundView from '@/views/NotFoundView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: Home },
    { path: '/:subsystem/:name/:mode?/:version?', name: 'editor', component: NodeView, props: true },
    { path: '/404', component: NotFoundView },
    { path: '/:pathMatch(.*)*', redirect: '/404' },
  ],
})

export function keyRoute(subsystem: string, name: string, mode: string | undefined, version: number) {
  return { name: 'editor', params: { subsystem, name, mode, version: `v${version}` } } as const
}

export default router
