import { onBeforeUnmount } from 'vue'

export type ScrollSide = 'left' | 'right'

function otherSide(side: ScrollSide): ScrollSide {
  return side === 'left' ? 'right' : 'left'
}

/** Mirrors vertical scroll between same-index elements, and horizontal between the side containers. */
export function useSyncedScroll() {
  const bound = new Map<string, { el: HTMLElement; listener: () => void }>()
  // avoids the mirrored scroll write re-triggering its own peer's listener
  let syncing = false

  function mirror(side: ScrollSide, peerKey: string, axis: 'scrollTop' | 'scrollLeft') {
    return () => {
      if (syncing) return
      const el = bound.get(`${side}:${peerKey}`)?.el
      const peer = bound.get(`${otherSide(side)}:${peerKey}`)?.el
      if (!el || !peer || peer[axis] === el[axis]) return
      syncing = true
      peer[axis] = el[axis]
      syncing = false
    }
  }

  function bind(mapKey: string, el: Element | null, listener: () => void) {
    const prev = bound.get(mapKey)
    if (prev) prev.el.removeEventListener('scroll', prev.listener)
    bound.delete(mapKey)

    if (!el || !(el instanceof HTMLElement)) return
    el.addEventListener('scroll', listener)
    bound.set(mapKey, { el, listener })
  }

  /** Bind as a template ref callback: `:ref="(el) => register(index, side, el)"`. */
  function register(index: number, side: ScrollSide, el: Element | null) {
    bind(`${side}:col${index}`, el, mirror(side, `col${index}`, 'scrollTop'))
  }

  /** Bind the per-side horizontal scroller: `:ref="(el) => registerRow(side, el)"`. */
  function registerRow(side: ScrollSide, el: Element | null) {
    bind(`${side}:row`, el, mirror(side, 'row', 'scrollLeft'))
  }

  onBeforeUnmount(() => {
    for (const { el, listener } of bound.values()) el.removeEventListener('scroll', listener)
    bound.clear()
  })

  return { register, registerRow }
}
