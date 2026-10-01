import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createTelemetryTail, readTelemetryFull, TELEMETRY_INITIAL_TAIL_BYTES } from '../telemetry'
import type { TailFs } from '../activity'

let dir: string
let log: string

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ragx-tail-'))
  fs.mkdirSync(path.join(dir, '.ragx', 'logs'), { recursive: true })
  log = path.join(dir, '.ragx', 'logs', 'mcp.jsonl')
})
afterEach(() => fs.rmSync(dir, { recursive: true, force: true }))

const HOUR = 3600 * 1000
const iso = (msAgo: number): string => new Date(Date.now() - msAgo).toISOString()

function line(over: Record<string, unknown> = {}): string {
  return JSON.stringify({ ts: iso(HOUR), tool: 'search_hybrid', ms: 10, project: 'p', ...over })
}

/** O resumo precisa ser IDÊNTICO ao da leitura completa (menos a ordem de `callsByTool`, que vem de um Map). */
function normalize<T extends { callsByTool: Array<{ tool: string; count: number }> }>(s: T): T {
  return { ...s, callsByTool: [...s.callsByTool].sort((a, b) => a.tool.localeCompare(b.tool)) }
}

function expectSameAsFull(tail: ReturnType<typeof createTelemetryTail>, hours = 24): void {
  expect(normalize(tail.read(dir, hours))).toEqual(normalize(readTelemetryFull(dir, hours)))
}

describe('createTelemetryTail', () => {
  it('sem arquivo devolve zerado', () => {
    const tail = createTelemetryTail()
    expect(tail.read(dir, 24)).toMatchObject({ totalCalls: 0, lastCallAt: null, callsByTool: [] })
    expectSameAsFull(tail)
  })

  it('sem crescimento devolve o MESMO objeto (e não relê)', () => {
    fs.writeFileSync(log, [line(), line({ tool: 'build_context', tokens_delivered: 5, baseline_tokens: 50 })].join('\n') + '\n')
    const tail = createTelemetryTail()
    const a = tail.read(dir, 24)
    const b = tail.read(dir, 24)
    expect(b).toBe(a)
    expect(a.totalCalls).toBe(2)
  })

  it('com crescimento lê só o que foi acrescentado e soma ao que já tinha', () => {
    fs.writeFileSync(log, line() + '\n')
    const reads: Array<[number, number]> = []
    const io: TailFs = {
      size: (f) => (fs.existsSync(f) ? fs.statSync(f).size : null),
      read: (f, s, e) => fs.readFileSync(f).subarray(s, e).toString('utf8'),
      readBytes: (f, s, e) => {
        reads.push([s, e])
        return fs.readFileSync(f).subarray(s, e)
      },
    }
    const tail = createTelemetryTail(io)
    tail.read(dir, 24)
    const offset = fs.statSync(log).size
    fs.appendFileSync(log, line({ tool: 'get_chunk' }) + '\n')
    const s = tail.read(dir, 24)
    expect(s.totalCalls).toBe(2)
    expect(reads.at(-1)?.[0]).toBe(offset) // a segunda leitura começou onde a primeira parou
    expectSameAsFull(tail)
  })

  it('linha parcial (escrita em andamento) espera a volta, sem contar nem perder', () => {
    fs.writeFileSync(log, line() + '\n')
    const tail = createTelemetryTail()
    tail.read(dir, 24)
    const completa = line({ tool: 'get_chunk' })
    fs.appendFileSync(log, completa.slice(0, 20)) // sem quebra de linha
    expect(tail.read(dir, 24).totalCalls).toBe(1)
    fs.appendFileSync(log, completa.slice(20) + '\n')
    expect(tail.read(dir, 24).totalCalls).toBe(2)
    expectSameAsFull(tail)
  })

  it('caractere multibyte cortado no meio de duas leituras não desalinha o deslocamento', () => {
    fs.writeFileSync(log, line() + '\n')
    const tail = createTelemetryTail()
    tail.read(dir, 24)
    const bytes = Buffer.from(line({ tool: 'bússola-çã' }) + '\n', 'utf8')
    const corte = bytes.indexOf(0xc3) + 1 // no meio de um `ú`
    fs.appendFileSync(log, bytes.subarray(0, corte))
    tail.read(dir, 24)
    fs.appendFileSync(log, bytes.subarray(corte))
    const s = tail.read(dir, 24)
    expect(s.callsByTool.map((c) => c.tool).sort()).toEqual(['bússola-çã', 'search_hybrid'])
    expectSameAsFull(tail)
  })

  it('arquivo que encolheu (truncado) ou foi substituído (outra assinatura) é relido do zero', () => {
    fs.writeFileSync(log, [line(), line(), line()].join('\n') + '\n')
    let assinatura = 'a'
    const io: TailFs = {
      size: (f) => (fs.existsSync(f) ? fs.statSync(f).size : null),
      read: (f, s, e) => fs.readFileSync(f).subarray(s, e).toString('utf8'),
      signature: () => assinatura,
    }
    const tail = createTelemetryTail(io)
    expect(tail.read(dir, 24).totalCalls).toBe(3)
    fs.writeFileSync(log, line() + '\n') // truncou: menor que o deslocamento
    expect(tail.read(dir, 24).totalCalls).toBe(1)
    // substituído por outro arquivo MAIOR (rotação seguida de muita escrita): só a assinatura denuncia
    fs.writeFileSync(log, [line(), line(), line(), line(), line()].join('\n') + '\n')
    assinatura = 'b'
    expect(tail.read(dir, 24).totalCalls).toBe(5)
  })

  it('linhas corrompidas e que não são objetos não quebram nem contam', () => {
    fs.writeFileSync(log, ['lixo', 'null', '123', '"texto"', line(), '{"ts":'].join('\n') + '\n')
    const tail = createTelemetryTail()
    expect(tail.read(dir, 24).totalCalls).toBe(1)
    expectSameAsFull(tail)
  })

  it('linha sem ts válido conta nos totais, como na leitura completa', () => {
    fs.writeFileSync(log, [line({ ts: 'ontem' }), line({ ts: undefined }), line()].join('\n') + '\n')
    const tail = createTelemetryTail()
    expectSameAsFull(tail)
    expect(tail.read(dir, 24).totalCalls).toBe(3)
  })

  it('a janela anda com o tempo: entrada que passa de 24 h sai sem reler o arquivo', () => {
    let agora = Date.now()
    const entrada = new Date(agora - 23 * HOUR).toISOString()
    fs.writeFileSync(log, line({ ts: entrada }) + '\n')
    const tail = createTelemetryTail(undefined, () => agora)
    const a = tail.read(dir, 24)
    expect(a.totalCalls).toBe(1)
    agora += 2 * HOUR // a entrada agora tem 25 h
    const b = tail.read(dir, 24)
    expect(b.totalCalls).toBe(0)
    expect(b).not.toBe(a)
    expect(b.lastCallAt).toBe(entrada) // `lastCallAt` ignora a janela
  })

  it('a série de 14 dias soma só build_context com as duas medidas, por dia local', () => {
    fs.writeFileSync(
      log,
      [
        line({ tool: 'build_context', tokens_delivered: 10, baseline_tokens: 100 }),
        line({ tool: 'build_context', tokens_delivered: 20, baseline_tokens: 200, ts: iso(3 * 24 * HOUR) }),
        line({ tool: 'build_context', tokens_delivered: 5 }), // sem baseline: não conta
        line({ tool: 'build_context', tokens_delivered: 1, baseline_tokens: 9, ts: iso(30 * 24 * HOUR) }), // fora de 14 dias
      ].join('\n') + '\n',
    )
    const tail = createTelemetryTail()
    const s = tail.read(dir, 24)
    expect(s.savings).toMatchObject({ baseline: 300, delivered: 30, calls: 2 })
    expectSameAsFull(tail)
  })

  it('uma janela maior que a guardada relê (sem perder entradas)', () => {
    fs.writeFileSync(log, [line({ ts: iso(30 * HOUR) }), line()].join('\n') + '\n')
    const tail = createTelemetryTail()
    expect(tail.read(dir, 24).totalCalls).toBe(1)
    expect(tail.read(dir, 48).totalCalls).toBe(2)
    expectSameAsFull(tail, 48)
  })

  it('primeira leitura de um arquivo grande pega só os últimos 4 MB e descarta a linha cortada', () => {
    const recente = line({ tool: 'build_context', tokens_delivered: 7, baseline_tokens: 70 })
    const enchimento = line({ tool: 'x' }) + '\n'
    const partes: string[] = []
    let tamanho = 0
    while (tamanho < TELEMETRY_INITIAL_TAIL_BYTES + 200_000) {
      partes.push(enchimento)
      tamanho += enchimento.length
    }
    fs.writeFileSync(log, partes.join('') + recente + '\n')
    const tail = createTelemetryTail()
    const s = tail.read(dir, 24)
    // leu menos linhas do que o arquivo tem, mas viu a última inteira e nenhuma cortada
    expect(s.totalCalls).toBeLessThan(partes.length + 1)
    expect(s.totalCalls).toBeGreaterThan(1000)
    expect(s.savings).toMatchObject({ baseline: 70, delivered: 7, calls: 1 })
    fs.appendFileSync(log, line() + '\n')
    expect(tail.read(dir, 24).totalCalls).toBe(s.totalCalls + 1)
  })

  it('arquivo menor que 4 MB lê também o `mcp.jsonl.1` da rotação, uma vez', () => {
    fs.writeFileSync(`${log}.1`, [line({ tool: 'antigo' }), line({ tool: 'antigo' })].join('\n') + '\n')
    fs.writeFileSync(log, line() + '\n')
    const tail = createTelemetryTail()
    const s = tail.read(dir, 24)
    expect(s.callsByTool.find((c) => c.tool === 'antigo')?.count).toBe(2)
    expect(tail.read(dir, 24)).toBe(s)
    fs.appendFileSync(log, line() + '\n')
    expect(tail.read(dir, 24).callsByTool.find((c) => c.tool === 'antigo')?.count).toBe(2) // não relê o .1
  })

  it('PROPRIEDADE: linhas aleatórias, corrompidas e escritas parciais batem com a leitura completa a cada passo', () => {
    let seed = 12345
    const rnd = (): number => {
      seed = (seed * 1664525 + 1013904223) % 4294967296
      return seed / 4294967296
    }
    const tools = ['search_hybrid', 'build_context', 'get_chunk', 'refresh', 'ação-ç']
    const tail = createTelemetryTail()
    fs.writeFileSync(log, '')
    for (let passo = 0; passo < 60; passo++) {
      let texto = ''
      const n = Math.floor(rnd() * 5)
      for (let i = 0; i < n; i++) {
        const r = rnd()
        if (r < 0.1) texto += 'linha corrompida {{\n'
        else if (r < 0.15) texto += 'null\n'
        else {
          texto +=
            line({
              tool: tools[Math.floor(rnd() * tools.length)],
              ts: rnd() < 0.05 ? 'sem-data' : iso(Math.floor(rnd() * 60 * HOUR)),
              tokens_delivered: rnd() < 0.7 ? Math.floor(rnd() * 900) : undefined,
              baseline_tokens: rnd() < 0.7 ? Math.floor(rnd() * 5000) : undefined,
            }) + '\n'
        }
      }
      // às vezes a escrita termina no meio de uma linha, e o resto vem no passo seguinte
      if (rnd() < 0.3 && texto.length > 10) {
        const bytes = Buffer.from(texto, 'utf8')
        const corte = Math.floor(bytes.length * rnd())
        fs.appendFileSync(log, bytes.subarray(0, corte))
        // um corte logo antes da quebra deixa um JSON completo SEM `\n`: a leitura completa o conta e a
        // incremental espera a quebra de linha (por isso a comparação só vale quando a ponta não é JSON)
        const ponta = bytes.subarray(0, corte).toString('utf8').split('\n').pop() ?? ''
        let pontaValida: boolean
        try {
          JSON.parse(ponta)
          pontaValida = ponta.trim() !== ''
        } catch {
          pontaValida = false
        }
        if (!pontaValida) expectSameAsFull(tail)
        fs.appendFileSync(log, bytes.subarray(corte))
      } else {
        fs.appendFileSync(log, texto)
      }
      expectSameAsFull(tail)
    }
  })
})
