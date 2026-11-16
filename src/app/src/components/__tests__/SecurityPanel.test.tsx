import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { SecurityPanel } from '../SecurityPanel'
import { installBridge } from '../../test/snap'
import type { SecurityScanResult } from '../../types/ragx-bridge'

const BASE: SecurityScanResult = {
  root: 'C:/proj/a',
  scanned: 17917,
  blocked: [],
  redacted: [],
  skipped: 217,
  ruleset: { version: 'builtin@1', rules: 30, disabled: [] },
  policy: 'strict',
}

async function rodar(result: SecurityScanResult) {
  installBridge({ runSecurityScan: vi.fn().mockResolvedValue(result) })
  render(<SecurityPanel projectId="scan-a" projectPath="C:/proj/a" />)
  fireEvent.click(screen.getByRole('button', { name: 'Atualizar achados de segurança' }))
  await screen.findByText(/Nenhum segredo encontrado/)
}

describe('SecurityPanel', () => {
  it('com cache, diz quantos arquivos não foram relidos e como reler tudo', async () => {
    await rodar({ ...BASE, mode: 'cache', reused: 14948 })
    expect(screen.getByText(/14\.948 arquivos já examinados pelo índice não foram relidos/)).toBeInTheDocument()
    expect(screen.getByText('ragx security scan .')).toBeInTheDocument()
  })

  it('varredura completa (ou CLI antiga, sem o campo) não mostra o aviso', async () => {
    await rodar({ ...BASE, mode: 'full' })
    expect(screen.queryByText(/não foram relidos/)).not.toBeInTheDocument()
  })

  it('mostra o erro da CLI em vez de deixar a tela vazia', async () => {
    installBridge({
      runSecurityScan: vi.fn().mockRejectedValue(new Error('ragx security scan . --json --cached excedeu o tempo limite de 180s')),
    })
    render(<SecurityPanel projectId="scan-b" projectPath="C:/proj/b" />)
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar achados de segurança' }))
    expect(await screen.findByText(/excedeu o tempo limite de 180s/)).toBeInTheDocument()
  })
})
