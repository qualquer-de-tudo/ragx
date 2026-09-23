import { describe, expect, it } from 'vitest'
import { JobQueue, defaultSpawn, type SpawnFn, type QueueDeps } from '../queue'
import type { ResolvedJob } from '../catalog'
import type { JobView } from '../../../src/types/ragx-bridge'

function fakeSpawn() {
  const children: Array<{
    cmd: string
    args: string[]
    cwd: string | null
    out: (l: string) => void
    err: (l: string) => void
    exit: (c: number | null) => void
    killed: boolean
  }> = []
  const spawn: SpawnFn = (cmd, args, cwd) => {
    let out: (l: string) => void = () => {}
    let err: (l: string) => void = () => {}
    let exit: (c: number | null) => void = () => {}
    const child = {
      cmd,
      args,
      cwd,
      out: (l: string) => out(l),
      err: (l: string) => err(l),
      exit: (c: number | null) => exit(c),
      killed: false,
    }
    children.push(child)
    return {
      onStdoutLine: (cb: (l: string) => void) => {
        out = cb
      },
      onStderrLine: (cb: (l: string) => void) => {
        err = cb
      },
      onExit: (cb: (c: number | null) => void) => {
        exit = cb
      },
      kill: () => {
        child.killed = true
        exit(null)
      },
    }
  }
  return { spawn, children }
}

function job(over: Partial<ResolvedJob> = {}): ResolvedJob {
  const base = {
    kind: 'update' as const,
    label: 'Atualizar Projeto',
    projectId: 'p1' as string | null,
    steps: [{ cmd: 'ragx' as const, args: ['index', 'C:/p1', '--progress', '--source', 'panel'], cwd: null, progress: true }],
  }
  const merged = { ...base, ...over }
  // Segue o mesmo formato geral do `catalog.ts` (`${kind}|${projectId ?? ''}|`)
  // a menos que o teste passe um `dedupeKey` explícito - assim, sobrescrever
  // `projectId`/`kind` no helper não deixa o dedupe comparando uma chave
  // desatualizada.
  return { ...merged, dedupeKey: over.dedupeKey ?? `${merged.kind}|${merged.projectId ?? ''}|` }
}

function makeQueue(spawn: SpawnFn, over: Partial<Omit<QueueDeps, 'spawn'>> = {}) {
  let idCounter = 0
  let clock = 0
  const deps: QueueDeps = {
    spawn,
    now: () => clock,
    newId: () => `job-${++idCounter}`,
    ...over,
  }
  const changes: JobView[][] = []
  const queue = new JobQueue(deps, (jobs) => changes.push(jobs))
  return { queue, changes, setClock: (t: number) => (clock = t) }
}

function findView(views: JobView[], id: string): JobView {
  const v = views.find((j) => j.id === id)
  if (!v) throw new Error(`job ${id} nao encontrado na lista`)
  return v
}

describe('JobQueue - serial', () => {
  it('a segunda tarefa só começa quando a primeira sai', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j1 = queue.enqueue(job({ projectId: 'p1' }))
    const j2 = queue.enqueue(job({ projectId: 'p2' }))

    expect(children).toHaveLength(1)
    expect(findView(queue.list(), j1.id).state).toBe('running')
    expect(findView(queue.list(), j2.id).state).toBe('queued')

    children[0].exit(0)

    expect(children).toHaveLength(2)
    expect(findView(queue.list(), j1.id).state).toBe('done')
    expect(findView(queue.list(), j2.id).state).toBe('running')
  })
})

describe('JobQueue - passos em sequência', () => {
  it('só roda o próximo passo se o anterior sair com código 0', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j = queue.enqueue(
      job({
        steps: [
          { cmd: 'ragx', args: ['init', 'F'], cwd: null, progress: false },
          { cmd: 'ragx', args: ['index', 'F', '--progress', '--source', 'panel'], cwd: null, progress: true },
        ],
      }),
    )

    expect(children).toHaveLength(1)
    expect(findView(queue.list(), j.id).step).toBe(1)

    children[0].exit(0)

    expect(children).toHaveLength(2)
    expect(children[1].args).toEqual(['index', 'F', '--progress', '--source', 'panel'])
    expect(findView(queue.list(), j.id).step).toBe(2)
    expect(findView(queue.list(), j.id).state).toBe('running')
  })

  it('para no primeiro erro e não roda os passos seguintes', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j = queue.enqueue(
      job({
        steps: [
          { cmd: 'ragx', args: ['init', 'F'], cwd: null, progress: false },
          { cmd: 'ragx', args: ['index', 'F'], cwd: null, progress: true },
        ],
      }),
    )

    children[0].exit(1)

    expect(children).toHaveLength(1)
    expect(findView(queue.list(), j.id).state).toBe('failed')
  })
})

describe('JobQueue - dedupe', () => {
  it('mesmo kind+projeto ainda queued/running devolve a tarefa existente', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j1 = queue.enqueue(job({ kind: 'update', projectId: 'p1' }))
    const j2 = queue.enqueue(job({ kind: 'update', projectId: 'p1' }))

    expect(j2.id).toBe(j1.id)
    expect(children).toHaveLength(1)
    expect(queue.list().filter((v) => v.kind === 'update' && v.projectId === 'p1')).toHaveLength(1)
  })

  it('depois que a tarefa termina, um novo enqueue cria uma nova', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j1 = queue.enqueue(job({ kind: 'update', projectId: 'p1' }))
    children[0].exit(0)
    const j2 = queue.enqueue(job({ kind: 'update', projectId: 'p1' }))

    expect(j2.id).not.toBe(j1.id)
    expect(children).toHaveLength(2)
  })

  // Fix round 1: dedupeKey (kind+projectId sozinho colidia `ollama-pull` de
  // modelos diferentes e `add-project` de pastas diferentes, porque os dois
  // têm `projectId: null` sempre).
  it('ollama-pull com modelos diferentes: os dois entram na fila', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j1 = queue.enqueue(
      job({
        kind: 'ollama-pull',
        projectId: null,
        dedupeKey: 'ollama-pull||nomic-embed-text',
        steps: [{ cmd: 'docker', args: ['exec', 'ollama', 'ollama', 'pull', 'nomic-embed-text'], cwd: null, progress: false }],
      }),
    )
    const j2 = queue.enqueue(
      job({
        kind: 'ollama-pull',
        projectId: null,
        dedupeKey: 'ollama-pull||mxbai-embed-large',
        steps: [{ cmd: 'docker', args: ['exec', 'ollama', 'ollama', 'pull', 'mxbai-embed-large'], cwd: null, progress: false }],
      }),
    )

    expect(j2.id).not.toBe(j1.id)
    expect(queue.list().filter((v) => v.kind === 'ollama-pull')).toHaveLength(2)
    // Fila serial: só o primeiro pedido spawna imediatamente, o segundo
    // fica `queued` até o primeiro sair.
    expect(children).toHaveLength(1)
  })

  it('ollama-pull com o mesmo modelo duas vezes: dedupe normalmente', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const ollamaPull = () =>
      job({
        kind: 'ollama-pull',
        projectId: null,
        dedupeKey: 'ollama-pull||nomic-embed-text',
        steps: [{ cmd: 'docker', args: ['exec', 'ollama', 'ollama', 'pull', 'nomic-embed-text'], cwd: null, progress: false }],
      })

    const j1 = queue.enqueue(ollamaPull())
    const j2 = queue.enqueue(ollamaPull())

    expect(j2.id).toBe(j1.id)
    expect(children).toHaveLength(1)
  })

  it('add-project com tokens de pasta diferentes: os dois entram na fila', () => {
    const { spawn } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j1 = queue.enqueue(
      job({
        kind: 'add-project',
        projectId: null,
        dedupeKey: 'add-project|C:/pastas/A',
        steps: [{ cmd: 'ragx', args: ['init', 'C:/pastas/A'], cwd: null, progress: false }],
      }),
    )
    const j2 = queue.enqueue(
      job({
        kind: 'add-project',
        projectId: null,
        dedupeKey: 'add-project|C:/pastas/B',
        steps: [{ cmd: 'ragx', args: ['init', 'C:/pastas/B'], cwd: null, progress: false }],
      }),
    )

    expect(j2.id).not.toBe(j1.id)
    expect(queue.list().filter((v) => v.kind === 'add-project')).toHaveLength(2)
  })
})

describe('JobQueue - progresso e previsão', () => {
  it('embed: eta e taxa calculadas a partir do início da fase', () => {
    const { spawn, children } = fakeSpawn()
    const { queue, setClock } = makeQueue(spawn)

    const j = queue.enqueue(job())
    setClock(0)
    children[0].out(JSON.stringify({ phase: 'embed', done: 10, total: 200 }))

    setClock(10_000)
    children[0].out(JSON.stringify({ phase: 'embed', done: 50, total: 200 }))

    const view = findView(queue.list(), j.id)
    expect(view.phase).toBe('embed')
    expect(view.done).toBe(50)
    expect(view.total).toBe(200)
    expect(view.etaSeconds).toBe(30)
    expect(view.ratePerSecond).toBe(5)
  })

  it('ratePerSecond só é preenchido na fase embed', () => {
    const { spawn, children } = fakeSpawn()
    const { queue, setClock } = makeQueue(spawn)

    const j = queue.enqueue(job())
    setClock(0)
    children[0].out(JSON.stringify({ phase: 'scan', done: 5, total: null }))
    setClock(5_000)
    children[0].out(JSON.stringify({ phase: 'chunk', done: 4, total: 8 }))

    const view = findView(queue.list(), j.id)
    expect(view.phase).toBe('chunk')
    expect(view.ratePerSecond).toBeNull()
  })

  it('linhas que não são JSON reconhecido só vão para o log', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j = queue.enqueue(job())
    children[0].out('iniciando...')
    children[0].out('{"phase":"done","ok":true}')

    const view = findView(queue.list(), j.id)
    expect(view.phase).toBeNull()
    expect(view.logTail).toEqual(['iniciando...', '{"phase":"done","ok":true}'])
  })
})

describe('JobQueue - busy', () => {
  it('linha busy vira nota, e a tarefa termina done quando o processo sai com 0', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j = queue.enqueue(job())
    children[0].out(JSON.stringify({ phase: 'busy', pending: true, holder: { source: 'hook' } }))
    children[0].exit(0)

    const view = findView(queue.list(), j.id)
    expect(view.state).toBe('done')
    expect(view.note).toBe('Outra indexação estava rodando; este pedido ficou agendado.')
  })

  it('busy num passo do meio não impede os passos seguintes de rodar', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j = queue.enqueue(
      job({
        steps: [
          { cmd: 'ragx', args: ['index', 'P', '--progress', '--source', 'panel'], cwd: null, progress: true },
          { cmd: 'ragx', args: ['hooks', 'install', 'P'], cwd: null, progress: false },
        ],
      }),
    )
    children[0].out(JSON.stringify({ phase: 'busy', pending: true, holder: {} }))
    children[0].exit(0)

    expect(children).toHaveLength(2)
    children[1].exit(0)

    const view = findView(queue.list(), j.id)
    expect(view.state).toBe('done')
    expect(view.note).toBe('Outra indexação estava rodando; este pedido ficou agendado.')
  })
})

describe('JobQueue - falha', () => {
  it('guarda a última linha não vazia de stderr como erro, e o logTail combinado', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j = queue.enqueue(job())
    children[0].out('linha 1')
    children[0].err('aviso qualquer')
    children[0].err('erro fatal: falhou')
    children[0].err('')
    children[0].exit(1)

    const view = findView(queue.list(), j.id)
    expect(view.state).toBe('failed')
    expect(view.error).toBe('erro fatal: falhou')
    expect(view.logTail).toEqual(['linha 1', 'aviso qualquer', 'erro fatal: falhou', ''])
  })

  it('sem stderr, usa a última linha não vazia de stdout, truncada em 300 caracteres', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j = queue.enqueue(job())
    const longLine = 'x'.repeat(400)
    children[0].out(longLine)
    children[0].exit(1)

    const view = findView(queue.list(), j.id)
    expect(view.state).toBe('failed')
    expect(view.error).toHaveLength(300)
    expect(view.error).toBe(longLine.slice(0, 300))
  })

  it('logTail guarda só as últimas 20 linhas', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j = queue.enqueue(job())
    for (let i = 0; i < 25; i++) children[0].out(`linha ${i}`)
    children[0].exit(0)

    const view = findView(queue.list(), j.id)
    expect(view.logTail).toHaveLength(20)
    expect(view.logTail[0]).toBe('linha 5')
    expect(view.logTail[19]).toBe('linha 24')
  })
})

describe('JobQueue - cancel', () => {
  it('cancela uma tarefa na fila sem rodar', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    queue.enqueue(job({ projectId: 'p1' }))
    const j2 = queue.enqueue(job({ projectId: 'p2' }))

    const ok = queue.cancel(j2.id)
    expect(ok).toBe(true)
    expect(findView(queue.list(), j2.id).state).toBe('cancelled')

    children[0].exit(0)
    expect(children).toHaveLength(1)
    expect(queue.hasActive()).toBe(false)
  })

  it('cancela a tarefa rodando: mata o processo e vira cancelled quando sai', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    const j = queue.enqueue(job())
    const ok = queue.cancel(j.id)

    expect(ok).toBe(true)
    expect(children[0].killed).toBe(true)
    expect(findView(queue.list(), j.id).state).toBe('cancelled')
  })

  it('cancelar id desconhecido devolve false', () => {
    const { spawn } = fakeSpawn()
    const { queue } = makeQueue(spawn)
    expect(queue.cancel('nao-existe')).toBe(false)
  })
})

describe('JobQueue - busyProjectIds', () => {
  it('reflete as tarefas ativas (queued + running)', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    queue.enqueue(job({ projectId: 'p1' }))
    queue.enqueue(job({ kind: 'embed', projectId: 'p2' }))

    expect(queue.busyProjectIds()).toEqual(new Set(['p1', 'p2']))

    children[0].exit(0)
    children[1].exit(0)

    expect(queue.busyProjectIds()).toEqual(new Set())
  })
})

describe('JobQueue - list', () => {
  it('mostra ativas primeiro e limita a 20 terminadas', () => {
    const { spawn, children } = fakeSpawn()
    const { queue } = makeQueue(spawn)

    for (let i = 0; i < 25; i++) {
      queue.enqueue(job({ projectId: `p${i}` }))
      children[i].exit(0)
    }

    const active = queue.enqueue(job({ projectId: 'ativa' }))
    const views = queue.list()

    const finished = views.filter((v) => v.state === 'done')
    expect(finished).toHaveLength(20)
    expect(views[0].id).toBe(active.id)
    expect(views[0].state).toBe('running')
  })
})

describe('defaultSpawn', () => {
  it('quebra stdout em linhas mesmo quando uma linha chega em pedaços, e no fim solta o resto', async () => {
    const spawn = defaultSpawn()
    const script =
      "process.stdout.write('foo'); setTimeout(() => { process.stdout.write('bar\\nbaz'); process.exit(0); }, 20)"
    const child = spawn(process.execPath, ['-e', script], null)

    const lines: string[] = []
    let exited = false
    const done = new Promise<void>((resolve) => {
      child.onStdoutLine((l) => lines.push(l))
      child.onExit(() => {
        exited = true
        resolve()
      })
    })
    await done

    expect(exited).toBe(true)
    expect(lines).toEqual(['foobar', 'baz'])
  })
})
