import type { components } from '@/api-types'

type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']
type TreeOut = components['schemas']['TreeOut']
type CategoryMeta = { icon: string }

const CATEGORY: Record<string, CategoryMeta> = {
  algo: { icon: 'mdi-function-variant' },
  infra: { icon: 'mdi-server-network' },
  hardware: { icon: 'mdi-memory' },
  l1_menu: { icon: 'mdi-menu' },
  run_settings: { icon: 'mdi-tune-variant' },
  tcds: { icon: 'mdi-clock-outline' },
  external: { icon: 'mdi-key' },
}

export function iconFor(vertex: TreeOut | KeyChildMetaOut, isAlias: boolean): string {
  if (isAlias) return 'mdi-link'
  if (vertex.category === null) return 'mdi-folder-key-outline'
  return CATEGORY[vertex.category]?.icon ?? 'mdi-script-text-key'
}

// Unset format is not a yaml guess: it opens as plain text, with no schema attached.
export function languageFor(format: string | null | undefined): string {
  return format || 'plaintext'
}

type RankedVertex = { isAlias: boolean; category: string | null; alias: string }

function rank(vertex: RankedVertex): number {
  if (vertex.isAlias) return 2
  return vertex.category === null ? 0 : 1
}

// Direct bundles first, then direct leaf keys, then aliases, alphabetically
function compareByKindThenName(a: RankedVertex, b: RankedVertex): number {
  return rank(a) - rank(b) || a.alias.localeCompare(b.alias)
}

export function sortByKind<T>(items: T[], toRanked: (item: T) => RankedVertex): T[] {
  return items
    .map((item) => ({ item, ranked: toRanked(item) }))
    .sort((a, b) => compareByKindThenName(a.ranked, b.ranked))
    .map(({ item }) => item)
}
