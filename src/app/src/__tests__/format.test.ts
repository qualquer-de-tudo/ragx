import { describe, expect, it } from 'vitest'
import { formatEta, formatRelative } from '../format'

const now = new Date('2026-09-23T12:00:00Z')

describe('formatRelative', () => {
  it.each([
    ['2026-09-23T11:59:30Z', 'agora'],
    ['2026-09-23T11:55:00Z', 'há 5 min'],
    ['2026-09-23T10:00:00Z', 'há 2 h'],
    ['2026-09-22T11:00:00Z', 'há 1 dia'],
    ['2026-09-20T12:00:00Z', 'há 3 dias'],
  ])('%s → %s', (iso, text) => expect(formatRelative(iso, now)).toBe(text))
})

describe('formatEta', () => {
  it.each([[20, 'menos de 1 min'], [600, 'cerca de 10 min'], [7200, 'cerca de 2 h']])(
    '%i s → %s', (s, text) => expect(formatEta(s)).toBe(text),
  )
})
