import { useEffect, useState } from 'react'
import type { Snapshot } from '../types/ragx-bridge'

export function useSnapshot(): { snapshot: Snapshot | null } {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)

  useEffect(() => {
    let cancelled = false
    window.ragx.getSnapshot().then((s) => {
      if (!cancelled) setSnapshot(s)
    })
    const unsubscribe = window.ragx.onSnapshot((s) => setSnapshot(s))
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [])

  return { snapshot }
}
