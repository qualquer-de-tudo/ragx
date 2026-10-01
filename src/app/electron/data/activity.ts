import fs from 'node:fs'
import path from 'node:path'
import type { ActivityEvent, ActivityKind } from './types'
import { ADOPTION_DAYS, type AdoptionSession } from './adoption'

/** Janela do feed: o que passou disso sai da memória. */
export const ACTIVITY_WINDOW_MS = 24 * 60 * 60 * 1000
/** Teto de eventos guardados; o mais antigo sai primeiro. */
export const ACTIVITY_MAX = 500
/** Na primeira leitura de um log, só o fim dele: um arquivo de meses não é lido inteiro. */
export const INITIAL_TAIL_BYTES = 512 * 1024

const LOGS = ['mcp.jsonl', 'cli.jsonl'] as const

export interface ActivitySource {
  id: string
  name: string
  path: string | null
}

export interface TailFs {
  size(file: string): number | null
  read(file: string, start: number, end: number): string
  /**
   * Os mesmos bytes, sem decodificar (RAGX-0174): o deslocamento é em BYTES, e um caractere multibyte
   * cortado no meio não pode desalinhar a leitura seguinte. Opcional: sem ela, usa `read`.
   */
  readBytes?(file: string, start: number, end: number): Buffer
  /** `ino` + `birthtimeMs`: muda quando o arquivo é substituído (rotação), mesmo que o tamanho não encolha. */
  signature?(file: string): string | null
}

export const nodeTailFs: TailFs = {
  size(file) {
    try {
      return fs.statSync(file).size
    } catch {
      return null
    }
  },
  read(file, start, end) {
    return this.readBytes!(file, start, end).toString('utf8')
  },
  readBytes(file, start, end) {
    const fd = fs.openSync(file, 'r')
    try {
      const buf = Buffer.alloc(end - start)
      const n = fs.readSync(fd, buf, 0, buf.length, start)
      return buf.subarray(0, n)
    } finally {
      fs.closeSync(fd)
    }
  },
  signature(file) {
    try {
      const st = fs.statSync(file)
      return `${st.ino}:${st.birthtimeMs}`
    } catch {
      return null
    }
  },
}

interface FileState {
  offset: number
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.length > 0 ? v : null
}

/** Uma linha do log vira evento; linha que não é o que se espera vira `null`, nunca exceção. */
export function parseLine(line: string, source: ActivitySource, log: 'mcp.jsonl' | 'cli.jsonl', id: string): ActivityEvent | null {
  let raw: unknown
  try {
    raw = JSON.parse(line)
  } catch {
    return null
  }
  if (typeof raw !== 'object' || raw === null) return null
  const r = raw as Record<string, unknown>
  const ts = str(r.ts)
  if (ts === null || Number.isNaN(Date.parse(ts))) return null
  let kind: ActivityKind
  let name: string | null
  if (log === 'mcp.jsonl') {
    kind = 'mcp'
    name = str(r.tool)
  } else {
    name = str(r.command)
    kind = name === 'session_start' ? 'session' : 'cli'
  }
  if (name === null) return null
  return {
    id,
    ts,
    projectId: source.id,
    projectName: source.name,
    kind,
    name,
    ms: num(r.ms),
    ok: typeof r.ok === 'boolean' ? r.ok : null,
    tokensDelivered: num(r.tokens_delivered),
    baselineTokens: num(r.baseline_tokens),
    errCode: str(r.err_code),
    respChars: num(r.resp_chars),
    respTokens: num(r.resp_tokens),
    client: str(r.client),
    profile: str(r.profile),
    session: str(r.session),
  }
}

/**
 * Acompanha os logs de atividade de cada projeto sem relê-los.
 *
 * Guarda, por arquivo, até onde já leu. A cada `poll`, lê só o que foi
 * acrescentado desde então e só até a última quebra de linha: uma linha no
 * meio de uma escrita fica para a próxima volta. Arquivo menor do que o
 * deslocamento foi truncado ou recriado, e a leitura recomeça do início.
 */
export class ActivityTail {
  private files = new Map<string, FileState>()
  private events: ActivityEvent[] = []
  /**
   * Índice leve por sessão (RAGX-0190), alimentado pelo mesmo `parseLine` e ANTES do corte de 24 h do `poll`: a adoção
   * olha 14 dias, e o feed só 24 h. Chave: projeto + sessão (o mesmo id em dois projetos não funde).
   */
  private sessionIndex = new Map<string, AdoptionSession>()

  constructor(
    private readonly deps: { fs: TailFs; now: () => number } = { fs: nodeTailFs, now: Date.now },
  ) {}

  /** Lê o que é novo em todos os projetos e devolve só os eventos novos, do mais antigo ao mais novo. */
  poll(sources: readonly ActivitySource[]): ActivityEvent[] {
    const novos: ActivityEvent[] = []
    for (const source of sources) {
      if (!source.path) continue
      for (const log of LOGS) {
        novos.push(...this.readNew(source, log))
      }
    }
    this.indexSessions(novos)
    const corte = this.deps.now() - ACTIVITY_WINDOW_MS
    const recentes = novos.filter((e) => Date.parse(e.ts) >= corte)
    recentes.sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts))
    this.events = [...this.events, ...recentes].filter((e) => Date.parse(e.ts) >= corte).slice(-ACTIVITY_MAX)
    return recentes
  }

  /** Sessões vistas na janela da adoção (14 dias), para `computeAdoption`. */
  sessions(): AdoptionSession[] {
    this.pruneSessions()
    return [...this.sessionIndex.values()]
  }

  private indexSessions(novos: readonly ActivityEvent[]): void {
    const corte = this.deps.now() - ADOPTION_DAYS * 86_400_000
    for (const e of novos) {
      if (Date.parse(e.ts) < corte) continue
      const key = `${e.projectId}\u0000${e.session ?? ''}`
      let s = this.sessionIndex.get(key)
      if (!s) {
        s = { projectId: e.projectId, projectName: e.projectName, session: e.session, startedAt: null, firstAt: e.ts, lastAt: e.ts, calls: 0, events: 0 }
        this.sessionIndex.set(key, s)
      }
      s.events += 1
      if (Date.parse(e.ts) < Date.parse(s.firstAt)) s.firstAt = e.ts
      if (Date.parse(e.ts) > Date.parse(s.lastAt)) s.lastAt = e.ts
      if (e.kind === 'session') {
        if (s.startedAt === null || Date.parse(e.ts) < Date.parse(s.startedAt)) s.startedAt = e.ts
      } else {
        s.calls += 1
      }
    }
  }

  private pruneSessions(): void {
    const corte = this.deps.now() - ADOPTION_DAYS * 86_400_000
    for (const [k, s] of this.sessionIndex) if (Date.parse(s.lastAt) < corte) this.sessionIndex.delete(k)
  }

  /** O que está em memória, do mais antigo ao mais novo. */
  recent(): ActivityEvent[] {
    const corte = this.deps.now() - ACTIVITY_WINDOW_MS
    return this.events.filter((e) => Date.parse(e.ts) >= corte)
  }

  private readNew(source: ActivitySource, log: 'mcp.jsonl' | 'cli.jsonl'): ActivityEvent[] {
    const file = path.join(source.path as string, '.ragx', 'logs', log)
    const size = this.deps.fs.size(file)
    if (size === null) {
      this.files.delete(file)
      return []
    }
    let state = this.files.get(file)
    let primeira = false
    if (!state) {
      primeira = true
      state = { offset: Math.max(0, size - INITIAL_TAIL_BYTES) }
      this.files.set(file, state)
    } else if (size < state.offset) {
      state.offset = 0 // truncado ou recriado
    }
    if (size === state.offset) return []

    let texto: string
    try {
      texto = this.deps.fs.read(file, state.offset, size)
    } catch {
      return []
    }
    const inicio = state.offset
    // Começou no meio do arquivo: a primeira linha provavelmente está cortada.
    const pulo = primeira && inicio > 0 ? texto.indexOf('\n') + 1 : 0
    if (primeira && inicio > 0 && pulo === 0) return []
    const corpo = texto.slice(pulo)
    // Deslocamentos em BYTES: o texto pode ter acento, e o arquivo é UTF-8.
    const lidoAntes = Buffer.byteLength(texto.slice(0, pulo), 'utf8')
    const ultima = corpo.lastIndexOf('\n')
    if (ultima < 0) {
      state.offset = inicio + lidoAntes // linha ainda sendo escrita: espera a próxima volta
      return []
    }
    const completo = corpo.slice(0, ultima + 1)
    state.offset = inicio + lidoAntes + Buffer.byteLength(completo, 'utf8')

    const out: ActivityEvent[] = []
    let pos = inicio + lidoAntes
    for (const linha of completo.split('\n')) {
      const bytes = Buffer.byteLength(linha, 'utf8') + 1
      if (linha.trim()) {
        const ev = parseLine(linha, source, log, `${source.id}:${log}:${pos}`)
        if (ev) out.push(ev)
      }
      pos += bytes
    }
    return out
  }
}
