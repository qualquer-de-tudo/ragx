import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ProjectDetail } from '../ProjectDetail'
import type { ProjectSnapshot } from '../../types/ragx-bridge'

function makeProject(path: string | null): ProjectSnapshot {
  return {
    id: '1',
    name: 'projeto-a',
    path,
    exists: path !== null,
    embeddingModel: 'x',
    embeddingProvider: 'ollama',
    visibility: 'workspace',
    counts: { documents: 5, chunks: 10, embeddings: 10, pendingEmbeddings: 0 },
    countsUnavailableReason: null,
    index: { finishedAt: '2026-09-23T10:00:00Z', mode: 'incremental', source: 'cli', branch: 'main', commit: 'c1' },
    git: path !== null ? { branch: 'main', commit: 'c1' } : null,
    hooksInstalled: true,
    running: null,
    pending: false,
    lastError: null,
    hasStatusFile: path !== null,
    telemetry: { callsByTool: [], totalCalls: 0, tokensDelivered: 0, lastCallAt: null },
  }
}

// substituído na Task 8/9 do plano painel v2
describe.skip('ProjectDetail', () => {
  it('desabilita as acoes sob demanda e explica o motivo quando o projeto nao tem path local (só federação)', () => {
    render(<ProjectDetail project={makeProject(null)} />)

    expect(screen.getByRole('button', { name: /ver economia estimada/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /atualizar achados de segurança/i })).toBeDisabled()
    expect(
      screen.getAllByText(/disponível apenas para projetos clonados localmente/i),
    ).toHaveLength(2)
  })

  it('mantem as acoes sob demanda habilitadas quando o projeto tem path local', () => {
    render(<ProjectDetail project={makeProject('C:\\a')} />)

    expect(screen.getByRole('button', { name: /ver economia estimada/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /atualizar achados de segurança/i })).toBeEnabled()
    expect(
      screen.queryByText(/disponível apenas para projetos clonados localmente/i),
    ).not.toBeInTheDocument()
  })

  it('mostra a mensagem de erro real quando ragx trial falha (ex.: arquivo de queries ausente)', async () => {
    window.ragx = {
      getSnapshot: vi.fn(),
      onSnapshot: vi.fn(() => () => {}),
      runTrial: vi.fn().mockRejectedValue(new Error('ragx trial --json saiu com código 2: UsageError: queries.yaml não encontrado')),
      runSecurityScan: vi.fn(),
    }

    render(<ProjectDetail project={makeProject('C:\\a')} />)
    fireEvent.click(screen.getByRole('button', { name: /ver economia estimada/i }))

    await waitFor(() =>
      expect(screen.getByText(/não foi possível calcular agora: .*queries\.yaml não encontrado/i)).toBeInTheDocument(),
    )
  })

  it('mostra a mensagem de erro real quando ragx security scan falha', async () => {
    window.ragx = {
      getSnapshot: vi.fn(),
      onSnapshot: vi.fn(() => () => {}),
      runTrial: vi.fn(),
      runSecurityScan: vi.fn().mockRejectedValue(new Error('ragx não encontrado no PATH')),
    }

    render(<ProjectDetail project={makeProject('C:\\a')} />)
    fireEvent.click(screen.getByRole('button', { name: /atualizar achados de segurança/i }))

    await waitFor(() =>
      expect(screen.getByText(/não foi possível escanear agora: ragx não encontrado no path/i)).toBeInTheDocument(),
    )
  })
})

function bridge(overrides: Partial<typeof window.ragx>) {
  window.ragx = {
    getSnapshot: vi.fn(),
    onSnapshot: vi.fn(() => () => {}),
    runTrial: vi.fn(),
    runSecurityScan: vi.fn(),
    ...overrides,
  }
}

function withId(id: string): ProjectSnapshot {
  return { ...makeProject(`C:\\${id}`), id }
}

// substituído na Task 8/9 do plano painel v2
describe.skip('ProjectDetail — resultados sob demanda', () => {
  it('rotula a economia como estimativa e diz quando o RAGX gasta mais tokens', async () => {
    bridge({
      runTrial: vi.fn().mockResolvedValue({
        totals: { baseline_tokens: 1000, ragx_tokens: 1350, saved_ratio: -0.35, source_coverage: 0.5 },
      }),
    })
    render(<ProjectDetail project={withId('trial-neg')} />)
    expect(screen.getByText('estimativa')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /ver economia estimada/i }))

    await waitFor(() => expect(screen.getByText('mais tokens')).toBeInTheDocument())
    expect(screen.getByText('35%')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /recalcular estimativa/i })).toBeEnabled()
  })

  it('lista os arquivos bloqueados com severidade em texto e sem mostrar o trecho do segredo', async () => {
    bridge({
      runSecurityScan: vi.fn().mockResolvedValue({
        root: 'C:\\a', scanned: 40, skipped: 0, policy: 'strict',
        ruleset: { version: 'builtin@1', rules: 10, disabled: [] },
        blocked: [{ path: 'config/.env', rule: 'filename-deny:env', severity: 'critical', line: 3, preview: 'AKIA-SEGREDO' }],
        redacted: [{ path: 'docs/setup.md', findings: 2 }],
      }),
    })
    render(<ProjectDetail project={withId('scan-dirty')} />)
    fireEvent.click(screen.getByRole('button', { name: /atualizar achados de segurança/i }))

    await waitFor(() => expect(screen.getByText('.env')).toBeInTheDocument())
    expect(screen.getByText('config')).toBeInTheDocument()
    expect(screen.getByText(':3')).toBeInTheDocument()
    expect(screen.getByText(/crítico/)).toBeInTheDocument()
    expect(screen.getByText('filename-deny:env')).toBeInTheDocument()
    expect(screen.queryByText(/AKIA-SEGREDO/)).not.toBeInTheDocument()
  })

  it('confirma quando o scan não encontra nada', async () => {
    bridge({
      runSecurityScan: vi.fn().mockResolvedValue({
        root: 'C:\\a', scanned: 12, skipped: 0, policy: 'strict',
        ruleset: { version: 'builtin@1', rules: 10, disabled: [] },
        blocked: [], redacted: [],
      }),
    })
    render(<ProjectDetail project={withId('scan-clean')} />)
    fireEvent.click(screen.getByRole('button', { name: /atualizar achados de segurança/i }))

    await waitFor(() => expect(screen.getByText(/nenhum segredo encontrado em 12 arquivos/i)).toBeInTheDocument())
  })

  it('mantém o último resultado ao voltar para o projeto', async () => {
    bridge({
      runTrial: vi.fn().mockResolvedValue({
        totals: { baseline_tokens: 1000, ragx_tokens: 760, saved_ratio: 0.24, source_coverage: 0.63 },
      }),
    })
    const { unmount } = render(<ProjectDetail project={withId('trial-cache')} />)
    fireEvent.click(screen.getByRole('button', { name: /ver economia estimada/i }))
    await waitFor(() => expect(screen.getByText('menos tokens')).toBeInTheDocument())
    unmount()

    render(<ProjectDetail project={withId('trial-cache')} />)
    expect(screen.getByText('menos tokens')).toBeInTheDocument()
    expect(screen.getByText('24%')).toBeInTheDocument()
  })
})

// substituído na Task 8/9 do plano painel v2
describe.skip('ProjectDetail — cobertura de embeddings', () => {
  it('avisa quando nenhum chunk tem embedding e diz como corrigir', () => {
    const p = { ...makeProject('C:/x'), counts: { documents: 10, chunks: 200, embeddings: 0, pendingEmbeddings: 200 } }
    render(<ProjectDetail project={p} />)
    expect(screen.getByText(/nenhum chunk tem embedding/i)).toBeInTheDocument()
    expect(screen.getByText('ragx index --embed-only')).toBeInTheDocument()
  })

  it('não avisa quando todos os chunks têm embedding', () => {
    render(<ProjectDetail project={makeProject('C:/x')} />)
    expect(screen.queryByText(/embed-only/)).not.toBeInTheDocument()
  })
})
