import http from 'node:http'
import type { AddressInfo } from 'node:net'
import { describe, expect, it } from 'vitest'
import { defaultBenchDeps, runOllamaBenchmark } from '../benchmark'
import type { BenchDeps } from '../benchmark'

type Post = BenchDeps['httpPostJson']
interface PostCall {
  url: string
  body: { model: string; input: string[] }
}

interface Opts {
  post?: Post
  ps?: unknown
  model?: string | null
  times?: number[]
  baseUrl?: string
}

function make(o: Opts = {}): { deps: BenchDeps; posts: PostCall[] } {
  const posts: PostCall[] = []
  const times = [...(o.times ?? [1000, 3000])]
  const deps: BenchDeps = {
    httpPostJson:
      o.post ??
      (async (url, body) => {
        posts.push({ url, body: body as PostCall['body'] })
        return { status: 200, json: { embeddings: [] } }
      }),
    httpGetJson: async () => (o.ps === undefined ? null : o.ps),
    now: () => times.shift() ?? 0,
    model: o.model === undefined ? 'nomic-embed-text' : o.model,
    baseUrl: o.baseUrl,
  }
  return { deps, posts }
}

describe('runOllamaBenchmark', () => {
  it('caminho GPU: 64 textos em 2 s = 32,0/s', async () => {
    const { deps } = make({ ps: { models: [{ name: 'nomic-embed-text:latest', size_vram: 1073741824 }] } })
    const r = await runOllamaBenchmark(deps)
    expect(r.ok).toBe(true)
    expect(r.chunksPerSecond).toBe(32)
    expect(r.processor).toBe('gpu')
    expect(r.vramMB).toBe(1024)
    expect(r.model).toBe('nomic-embed-text')
    expect(r.error).toBeNull()
    expect(new Date(r.measuredAt).toISOString()).toBe(r.measuredAt)
  })

  it('arredonda a uma casa', async () => {
    const { deps } = make({ times: [0, 3000], ps: { models: [] } })
    const r = await runOllamaBenchmark(deps)
    expect(r.chunksPerSecond).toBe(21.3)
  })

  it('caminho CPU', async () => {
    const { deps } = make({ ps: { models: [{ name: 'nomic-embed-text', size_vram: 0 }] } })
    const r = await runOllamaBenchmark(deps)
    expect(r.ok).toBe(true)
    expect(r.processor).toBe('cpu')
    expect(r.vramMB).toBeNull()
  })

  it('modelo ausente em /api/ps vira unknown', async () => {
    const { deps } = make({ ps: { models: [{ name: 'outro', size_vram: 5 }] } })
    const r = await runOllamaBenchmark(deps)
    expect(r.ok).toBe(true)
    expect(r.processor).toBe('unknown')
    expect(r.vramMB).toBeNull()
  })

  it('resposta inesperada de /api/ps vira unknown', async () => {
    for (const ps of [null, 'x', { models: 3 }, { models: [null, 4] }]) {
      const r = await runOllamaBenchmark(make({ ps }).deps)
      expect(r.processor).toBe('unknown')
      expect(r.ok).toBe(true)
    }
  })

  it('Ollama fora do ar', async () => {
    const r = await runOllamaBenchmark(make({ post: async () => null }).deps)
    expect(r.ok).toBe(false)
    expect(r.error).toBe('O Ollama não respondeu em localhost:11434.')
    expect(r.chunksPerSecond).toBeNull()
    expect(r.processor).toBe('unknown')
  })

  it('modelo não baixado (404)', async () => {
    const post: Post = async () => ({ status: 404, json: { error: 'model "x" not found' } })
    const r = await runOllamaBenchmark(make({ post, model: 'x' }).deps)
    expect(r.ok).toBe(false)
    expect(r.error).toBe('O modelo x não está baixado neste Ollama.')
    expect(r.model).toBe('x')
  })

  it('corpo com error', async () => {
    const post: Post = async () => ({ status: 200, json: { error: 'boom' } })
    const r = await runOllamaBenchmark(make({ post }).deps)
    expect(r.ok).toBe(false)
    expect(r.error).toBe('Falha ao gerar embeddings: boom')
  })

  it('status diferente de 200 sem corpo legível', async () => {
    const post: Post = async () => ({ status: 500, json: null })
    const r = await runOllamaBenchmark(make({ post }).deps)
    expect(r.ok).toBe(false)
    expect(r.error).toBe('Falha ao gerar embeddings: HTTP 500')
  })

  it('falha em lote da medição vira erro', async () => {
    let n = 0
    const post: Post = async () => (++n === 3 ? { status: 500, json: { error: 'oom' } } : { status: 200, json: {} })
    const r = await runOllamaBenchmark(make({ post }).deps)
    expect(r.ok).toBe(false)
    expect(r.error).toBe('Falha ao gerar embeddings: oom')
  })

  it('exceção nos deps não rejeita', async () => {
    const post: Post = async () => {
      throw new Error('kaboom')
    }
    const r = await runOllamaBenchmark(make({ post }).deps)
    expect(r.ok).toBe(false)
    expect(r.error).toBe('Falha ao gerar embeddings: kaboom')

    const deps = make({ ps: { models: [] } }).deps
    deps.httpGetJson = async () => {
      throw new Error('ps')
    }
    const r2 = await runOllamaBenchmark(deps)
    expect(r2.ok).toBe(true)
    expect(r2.processor).toBe('unknown')
  })

  it('usa o modelo passado ou o padrão', async () => {
    const a = make({ model: 'bge-m3', ps: { models: [] } })
    await runOllamaBenchmark(a.deps)
    expect(new Set(a.posts.map((p) => p.body.model))).toEqual(new Set(['bge-m3']))
    const b = make({ model: null, ps: { models: [] } })
    const r = await runOllamaBenchmark(b.deps)
    expect(new Set(b.posts.map((p) => p.body.model))).toEqual(new Set(['nomic-embed-text']))
    expect(r.model).toBe('nomic-embed-text')
  })

  it('aquecimento e depois dois POSTs de 32 textos', async () => {
    const { deps, posts } = make({ ps: { models: [] } })
    await runOllamaBenchmark(deps)
    expect(posts).toHaveLength(3)
    expect(posts[0].url).toBe('http://localhost:11434/api/embed')
    expect(posts[0].body.input).toEqual(['aquecimento'])
    expect(posts[1].body.input).toHaveLength(32)
    expect(posts[2].body.input).toHaveLength(32)
    expect(new Set([...posts[1].body.input, ...posts[2].body.input]).size).toBe(64)
  })

  it('tempo zero não divide por zero', async () => {
    const r = await runOllamaBenchmark(make({ times: [5, 5], ps: { models: [] } }).deps)
    expect(r.ok).toBe(true)
    expect(Number.isFinite(r.chunksPerSecond)).toBe(true)
  })
})

describe('defaultBenchDeps', () => {
  it('POST real contra servidor local efêmero', async () => {
    const seen: string[] = []
    const server = http.createServer((req, res) => {
      let body = ''
      req.on('data', (c) => (body += c))
      req.on('end', () => {
        seen.push(`${req.method} ${req.url} ${body}`)
        if (req.url === '/bad') {
          res.writeHead(404, { 'content-type': 'application/json' })
          res.end('{"error":"nada"}')
        } else if (req.url === '/junk') {
          res.end('não é json')
        } else {
          res.writeHead(200, { 'content-type': 'application/json' })
          res.end('{"ok":true}')
        }
      })
    })
    await new Promise<void>((r) => server.listen(0, '127.0.0.1', r))
    const port = (server.address() as AddressInfo).port
    try {
      const d = defaultBenchDeps('m')
      expect(d.model).toBe('m')
      expect(d.baseUrl).toBe('http://localhost:11434')
      const base = `http://127.0.0.1:${port}`
      expect(await d.httpPostJson(`${base}/x`, { a: 1 }, 2000)).toEqual({ status: 200, json: { ok: true } })
      expect(seen[0]).toBe('POST /x {"a":1}')
      expect(await d.httpPostJson(`${base}/bad`, {}, 2000)).toEqual({ status: 404, json: { error: 'nada' } })
      expect(await d.httpPostJson(`${base}/junk`, {}, 2000)).toEqual({ status: 200, json: null })
    } finally {
      server.close()
    }
    expect(await defaultBenchDeps(null).httpPostJson(`http://127.0.0.1:${port}/x`, {}, 500)).toBeNull()
  })
})
