import {
  createRouter,
  createWebHistory,
  type Router,
  type RouteLocationNormalizedGeneric,
} from 'vue-router'
import HomeView from '@/views/HomeView.vue'
import EditorView from '@/views/EditorView.vue'
import NotFoundView from '@/views/NotFoundView.vue'
import { useChangesStore } from '@/stores/changes'
import { useNavStore } from '@/stores/nav'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string | ((to: RouteLocationNormalizedGeneric) => string)
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', component: HomeView, meta: { title: 'Keytree' } },
    {
      path: '/:subsystem/:name/:mode?/:version?',
      name: 'editor',
      component: EditorView,
      props: true,
      meta: {
        title: (to) => {
          const { subsystem, name, mode, version } = to.params as Record<string, string>
          return `${[subsystem, name, mode, version].filter(Boolean).join('/')} - Keytree`
        },
      },
    },
    { path: '/404', component: NotFoundView, meta: { title: 'Not Found - Keytree' } },
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

router.afterEach((to) => {
  const title = to.meta.title
  document.title = typeof title === 'function' ? title(to) : (title ?? 'Keytree')
})

/** 'pending' = the version a mode's staged edit would produce. */
export type VersionTarget = number | 'pending'

export function keyRoute(
  subsystem: string,
  name: string,
  mode: string | undefined,
  version: VersionTarget,
) {
  return {
    name: 'editor',
    params: { subsystem, name, mode, version: version === 'pending' ? 'pending' : `v${version}` },
  } as const
}

/** Reads back the `vN`/`pending` version segment written by keyRoute. */
export function parseVersion(v: string | undefined): VersionTarget | undefined {
  if (v === 'pending') return 'pending'
  if (!v || v[0] !== 'v') return undefined
  const n = Number(v.slice(1))
  return Number.isFinite(n) ? n : undefined
}

/** What a comparison is against: a mode of the routed namespace, at some version. */
export type DiffTarget = { mode: string; version: VersionTarget }

function formatDiffTarget(target: DiffTarget): string {
  return `${target.mode}/${target.version === 'pending' ? 'pending' : `v${target.version}`}`
}

/** Reads back the `mode/vN`/`mode/pending` value written by formatDiffTarget. */
export function parseDiffTarget(raw: string | undefined): DiffTarget | undefined {
  if (!raw) return undefined
  const i = raw.lastIndexOf('/')
  if (i < 0) return undefined
  const mode = raw.slice(0, i)
  const version = parseVersion(raw.slice(i + 1))
  return mode && version !== undefined ? { mode, version } : undefined
}

export function withDiffQuery(
  query: Record<string, string>,
  target: DiffTarget | undefined,
): Record<string, string> {
  const next = { ...query }
  if (target) next.diff = formatDiffTarget(target)
  else delete next.diff
  return next
}

type ResolvedDiffRoot = {
  subsystem: string
  name: string
  mode: string
  version: number
  pending: boolean
}

/** Resolves a 'pending' target's version; undefined if it has no staged edit to resolve against. */
export function resolveDiffRoot(
  base: { subsystem: string; name: string },
  target: DiffTarget,
  pendingVersion: (mode: string) => number | undefined,
): ResolvedDiffRoot | undefined {
  if (target.version === 'pending') {
    const version = pendingVersion(target.mode)
    return version === undefined
      ? undefined
      : { ...base, mode: target.mode, version, pending: true }
  }
  return { ...base, mode: target.mode, version: target.version, pending: false }
}

/** Navigates into diff mode, remembering where to return to; null fromVersion means nothing to diff against. */
export function pushDiffRoute(
  router: Router,
  subsystem: string,
  name: string,
  mode: string,
  fromVersion: VersionTarget | null,
  target: DiffTarget,
) {
  if (fromVersion === null) {
    router.push(keyRoute(subsystem, name, mode, target.version))
    return
  }
  if (!router.currentRoute.value.query.diff) {
    useNavStore().preDiffLocation = router.currentRoute.value.fullPath
  }
  router.push({
    ...keyRoute(subsystem, name, mode, fromVersion),
    query: withDiffQuery({}, target),
  })
}

export default router
