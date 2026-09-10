import type { components } from '@/api-types'

type KeyChildMetaOut = components['schemas']['KeyChildMetaOut']
type TreeOut = components['schemas']['TreeOut']
type CategoryMeta = { icon: string; format?: 'xml' | 'yaml' | 'plaintext' }

export const CATEGORY: Record<string, CategoryMeta> = {
  algo: { icon: 'mdi-function-variant', format: 'xml' },
  infra: { icon: 'mdi-server-network', format: 'xml' },
  hardware: { icon: 'mdi-memory', format: 'xml' },
  l1_menu: { icon: 'mdi-menu', format: 'xml' },
  run_settings: { icon: 'mdi-tune-variant', format: 'xml' },
  tcds: { icon: 'mdi-clock-outline', format: 'plaintext' },
  external: { icon: 'mdi-key' },
}

export function iconFor(node: TreeOut | KeyChildMetaOut, isAlias: boolean): string {
  if (isAlias) return 'mdi-link'
  if (node.category === null) return 'mdi-folder-key-outline'
  return CATEGORY[node.category]?.icon ?? 'mdi-script-text-key'
}

type RankedNode = { isAlias: boolean; category: string | null; alias: string }

function rank(node: RankedNode): number {
  if (node.isAlias) return 2
  return node.category === null ? 0 : 1
}

// Direct bundles first, then direct leaf keys, then aliases, alphabetically
export function compareByKindThenName(a: RankedNode, b: RankedNode): number {
  return rank(a) - rank(b) || a.alias.localeCompare(b.alias)
}

export function sortByKind<T>(items: T[], toRanked: (item: T) => RankedNode): T[] {
  return items
    .map((item) => ({ item, ranked: toRanked(item) }))
    .sort((a, b) => compareByKindThenName(a.ranked, b.ranked))
    .map(({ item }) => item)
}
