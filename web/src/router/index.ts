import { createRouter, createWebHistory, type RouteLocationNormalizedGeneric } from 'vue-router'
import HomeView from '@/views/HomeView.vue'
import EditorView from '@/views/EditorView.vue'
import NotFoundView from '@/views/NotFoundView.vue'
import { useChangesStore } from '@/stores/changes'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: HomeView },
    {
      path: '/:subsystem/:name/:mode?/:version?',
      name: 'editor',
      component: EditorView,
      props: true,
    },
    { path: '/404', component: NotFoundView },
    { path: '/:pathMatch(.*)*', redirect: '/404' },
  ],
})

function sameKey(a: RouteLocationNormalizedGeneric, b: RouteLocationNormalizedGeneric): boolean {
  if (a.name !== b.name) return false
  return Object.keys(a.params).every((k) => a.params[k] === b.params[k])
}

router.beforeEach(async (to, from) => {
  if (sameKey(to, from)) return
  const changes = useChangesStore()
  if (!(await changes.confirmDiscard())) return false
})

export function keyRoute(
  subsystem: string,
  name: string,
  mode: string | undefined,
  version: number,
) {
  return { name: 'editor', params: { subsystem, name, mode, version: `v${version}` } } as const
}

/** Reads back the `vN` version segment written by keyRoute. */
export function parseVersion(v: string | undefined): number | undefined {
  if (!v || v[0] !== 'v') return undefined
  const n = Number(v.slice(1))
  return Number.isFinite(n) ? n : undefined
}

export default router
