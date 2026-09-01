type CategoryMeta = { icon: string; format?: 'xml' | 'yaml' | 'plaintext' }

export const CATEGORY: Record<string, CategoryMeta> = {
  run_settings: { icon: 'mdi-tune-variant', format: 'xml' },
  algo: { icon: 'mdi-function-variant', format: 'xml' },
  infra: { icon: 'mdi-server-network', format: 'xml' },
  hardware: { icon: 'mdi-memory', format: 'xml' },
  tcds: { icon: 'mdi-clock-outline', format: 'plaintext' },
  l1_menu: { icon: 'mdi-menu', format: 'xml' },
  scalar: { icon: 'mdi-tag-outline' },
}
