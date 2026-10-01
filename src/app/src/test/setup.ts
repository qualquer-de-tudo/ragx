import { afterEach } from 'vitest'
import { cleanup, configure } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { CACHE_KEY, resetCacheThrottle } from '../snapshotCache'

// Com a suíte inteira em paralelo o `findBy*` de 1 s (padrão) estourava em máquina carregada.
configure({ asyncUtilTimeout: 4000 })

// Node 25 traz um `localStorage` global sem os métodos (sem `--localstorage-file`) que esconde o do jsdom. Os testes
// que dependem de armazenamento (preferências de lista, cache do snapshot) ganham um em memória.
if (typeof window.localStorage?.setItem !== 'function') {
  const data = new Map<string, string>()
  const memory: Storage = {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, String(v)),
  }
  Object.defineProperty(window, 'localStorage', { value: memory, configurable: true })
}

afterEach(() => {
  cleanup()
  // O último snapshot fica em localStorage (RAGX-0182): sem isto, um teste herdaria o cache do anterior.
  try {
    window.localStorage.removeItem(CACHE_KEY)
  } catch {
    /* ambiente sem localStorage */
  }
  resetCacheThrottle()
})
