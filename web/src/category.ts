import type { components } from '@/api-types'

type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']
type TreeOut = components['schemas']['TreeOut']
type CategoryMeta = { icon: string; format?: string }

const CATEGORY: Record<string, CategoryMeta> = {
  algo: { icon: 'mdi-function-variant', format: 'yaml' },
  infra: { icon: 'mdi-server-network', format: 'yaml' },
  hardware: { icon: 'mdi-memory', format: 'yaml' },
  l1_menu: { icon: 'mdi-menu', format: 'yaml' },
  run_settings: { icon: 'mdi-tune-variant', format: 'yaml' },
  tcds: { icon: 'mdi-clock-outline', format: 'plaintext' },
  external: { icon: 'mdi-key' }, // no format, because external keys are not editable
}

export function iconFor(vertex: TreeOut | KeyChildMetaOut, isAlias: boolean): string {
  if (isAlias) return 'mdi-link'
  if (vertex.category === null) return 'mdi-folder-key-outline'
  return CATEGORY[vertex.category]?.icon ?? 'mdi-script-text-key'
}

export function languageFor(category: string | null | undefined): string {
  return (category && CATEGORY[category]?.format) || 'yaml'
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
