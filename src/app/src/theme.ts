/**
 * Tema do renderer (RAGX-0193): `dark` (padrão), `light` ou `system`. O renderer aplica `data-theme` com o tema
 * RESOLVIDO (`dark` ou `light`) em `document.documentElement`; sem `<script>` inline (a CSP de produção o proíbe), a
 * aplicação acontece em `main.tsx` antes de `createRoot`, com a preferência lida de `localStorage` (dentro de
 * `try/catch`) para não piscar, e confirmada depois por `getSettings`.
 */
export type ThemePref = 'dark' | 'light' | 'system'
export type ResolvedTheme = 'dark' | 'light'

export const THEME_PREFS: readonly ThemePref[] = ['dark', 'light', 'system']
const KEY = 'ragx.theme'
const QUERY = '(prefers-color-scheme: light)'

export function isThemePref(v: unknown): v is ThemePref {
  return v === 'dark' || v === 'light' || v === 'system'
}

/** `system` segue o sistema; os outros valem como estão. */
export function resolveTheme(pref: ThemePref, systemPrefersLight: boolean): ResolvedTheme {
  if (pref === 'system') return systemPrefersLight ? 'light' : 'dark'
  return pref
}

export function readStoredTheme(): ThemePref {
  try {
    const v = window.localStorage.getItem(KEY)
    return isThemePref(v) ? v : 'dark'
  } catch {
    return 'dark'
  }
}

export function storeTheme(pref: ThemePref): void {
  try {
    window.localStorage.setItem(KEY, pref)
  } catch {
    /* sem armazenamento: o tema vale só nesta sessão */
  }
}

function systemPrefersLight(): boolean {
  try {
    return typeof window.matchMedia === 'function' && window.matchMedia(QUERY).matches
  } catch {
    return false
  }
}

/** Aplica o tema resolvido em `<html data-theme>` e devolve qual foi. */
export function applyTheme(pref: ThemePref): ResolvedTheme {
  const resolved = resolveTheme(pref, systemPrefersLight())
  document.documentElement.dataset.theme = resolved
  return resolved
}

/** Com `system`, reaplica quando o sistema troca de claro para escuro. Devolve quem para de ouvir. */
export function watchSystemTheme(getPref: () => ThemePref): () => void {
  if (typeof window.matchMedia !== 'function') return () => {}
  const mq = window.matchMedia(QUERY)
  const listener = () => {
    if (getPref() === 'system') applyTheme('system')
  }
  mq.addEventListener('change', listener)
  return () => mq.removeEventListener('change', listener)
}

let current: ThemePref = 'dark'
export function currentTheme(): ThemePref {
  return current
}

/** Chamado por `main.tsx` antes de `createRoot`: aplica o último tema guardado, confirma pelo processo principal. */
export function initTheme(): void {
  current = readStoredTheme()
  applyTheme(current)
  watchSystemTheme(() => current)
  Promise.resolve()
    .then(() => window.ragx.getSettings())
    .then(
      (s) => setTheme(isThemePref(s.theme) ? s.theme : 'dark', false),
      () => {
        /* sem ponte (ou falha): fica o que estava guardado */
      },
    )
}

/** Troca na hora (sem reiniciar); `persist` também grava no processo principal. */
export function setTheme(pref: ThemePref, persist = true): Promise<void> {
  current = pref
  storeTheme(pref)
  applyTheme(pref)
  return persist ? window.ragx.setTheme(pref) : Promise.resolve()
}
