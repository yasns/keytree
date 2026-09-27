export const LOCALE = new Intl.Locale('en-GB')

const RTF = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })
const RTF_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
]

export function relativeTime(iso: string): string {
  const diffSeconds = (new Date(iso).getTime() - Date.now()) / 1000
  const [unit, secs] = RTF_UNITS.find(([, secs]) => Math.abs(diffSeconds) >= secs) ?? ['second', 1]
  return RTF.format(Math.round(diffSeconds / secs), unit)
}

export function pluralize(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}

const LIST_FORMAT = new Intl.ListFormat('en', { style: 'long', type: 'conjunction' })

export function formatList(items: string[]): string {
  return LIST_FORMAT.format(items)
}

export type MatchSegment = { text: string; matched: boolean }

/** Splits `text` into segments around the first case-insensitive match of `needle`. */
export function highlightMatch(text: string, needle: string): MatchSegment[] {
  if (!needle) return [{ text, matched: false }]
  const idx = text.toLowerCase().indexOf(needle.toLowerCase())
  if (idx === -1) return [{ text, matched: false }]
  const end = idx + needle.length
  return [
    { text: text.slice(0, idx), matched: false },
    { text: text.slice(idx, end), matched: true },
    { text: text.slice(end), matched: false },
  ].filter((seg) => seg.text.length > 0)
}
