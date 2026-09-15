/**
 * Cache com TTL e versão (§40).
 *
 * Duas regras que não se dobram:
 *
 *   1. **Nada que venha da tela de segurança entra aqui.** O chamador decide o
 *      que cachear; a lista de chaves permitidas é explícita, e não há atalho
 *      genérico que aceite qualquer coisa.
 *   2. **A chave carrega a versão do índice.** Depois de um `sync`, a chave
 *      muda sozinha e o dado velho expira — invalidação que depende de alguém
 *      lembrar de chamar `clear()` é invalidação que falha.
 */

const CACHEABLE = new Set([
  'dictionary', 'stats', 'documents', 'graph', 'entity',
  // Origens: nome, commit e contagem de fontes base e projetos do hub. Muda
  // raramente e custa três chamadas ao RAGX — mas nada de conteúdo entra aqui.
  'sources',
]);

interface Entry<T> {
  value: T;
  expiresAt: number;
  version: string;
}

export class Cache {
  private store = new Map<string, Entry<unknown>>();
  private version = '0';

  constructor(
    private enabled: boolean,
    private ttlMs = 60_000,
    private maxEntries = 200,
  ) {}

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
    if (!enabled) this.clear();
  }

  /** Chamado após sync/reindex: tudo que era válido deixa de ser. */
  bumpVersion(v: string): void {
    if (v !== this.version) {
      this.version = v;
      this.store.clear();
    }
  }

  get<T>(kind: string, key: string): T | undefined {
    if (!this.enabled || !CACHEABLE.has(kind)) return undefined;
    const entry = this.store.get(`${kind}:${key}`) as Entry<T> | undefined;
    if (!entry) return undefined;
    if (entry.version !== this.version || Date.now() > entry.expiresAt) {
      this.store.delete(`${kind}:${key}`);
      return undefined;
    }
    return entry.value;
  }

  set<T>(kind: string, key: string, value: T, ttlMs?: number): void {
    if (!this.enabled || !CACHEABLE.has(kind)) return;
    if (this.store.size >= this.maxEntries) {
      // Descarta o mais antigo. Map preserva ordem de inserção, então o
      // primeiro é o mais velho — LRU completo não paga o custo aqui.
      const primeiro = this.store.keys().next().value;
      if (primeiro) this.store.delete(primeiro);
    }
    this.store.set(`${kind}:${key}`, {
      value,
      expiresAt: Date.now() + (ttlMs ?? this.ttlMs),
      version: this.version,
    });
  }

  clear(): void {
    this.store.clear();
  }

  get size(): number {
    return this.store.size;
  }
}
