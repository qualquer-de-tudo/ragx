import { formatRelative } from '../../format'
import { useClock } from '../../hooks/useClock'

const MINUTE_MS = 60_000

/** "há 3 min" que avança sozinho: só esta folha assina o relógio de 60 s, o resto da tela não re-renderiza por isso. */
export function RelativeTime({ iso }: { iso: string }) {
  const now = useClock(MINUTE_MS)
  return <>{formatRelative(iso, new Date(now))}</>
}
