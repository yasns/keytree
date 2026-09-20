import type { components } from '@/api-types'

type ModeOut = components['schemas']['ModeOut']

/** Newest non-decommissioned version, or the true tip if every version is decommissioned. */
export function goodTip(mode: ModeOut): number | undefined {
  return mode.versions.find((v) => !mode.decommissioned_versions.includes(v)) ?? mode.versions[0]
}

export function versionLabel(mode: ModeOut, version: number, isLatest: boolean): string {
  const tags: string[] = []
  if (isLatest) tags.push('latest')
  if (mode.decommissioned_versions.includes(version)) tags.push('decommissioned')
  return tags.length ? `v${version} (${tags.join(', ')})` : `v${version}`
}
