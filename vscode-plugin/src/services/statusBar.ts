/**
 * Barra de status — uma entrada, e só quando diz algo útil (§27).
 */

import * as vscode from 'vscode';
import type { SystemState } from '../rag/types';

const ROTULOS: Record<SystemState, { icone: string; texto: string; dica: string }> = {
  ready: { icone: 'database', texto: 'Ready', dica: 'RAGX conectado e pronto' },
  indexing: { icone: 'sync~spin', texto: 'Indexing', dica: 'RAGX indexando' },
  syncing: { icone: 'sync~spin', texto: 'Syncing', dica: 'RAGX sincronizando' },
  outdated: {
    icone: 'warning',
    texto: 'Outdated',
    dica: 'O índice está atrás do working tree — rode Sync',
  },
  error: { icone: 'error', texto: 'Error', dica: 'Falha ao falar com o RAGX' },
  warning: { icone: 'warning', texto: 'Warning', dica: 'RAGX com ressalvas' },
  securityBlocked: {
    icone: 'shield',
    texto: 'Blocked',
    dica: 'Arquivos bloqueados pelo Security Gate',
  },
  disconnected: {
    icone: 'debug-disconnect',
    texto: 'Disconnected',
    dica: 'RAGX não conectado',
  },
};

export class StatusBar {
  private item: vscode.StatusBarItem;
  private visivel = true;

  constructor() {
    this.item = vscode.window.createStatusBarItem(
      'ragx.status',
      vscode.StatusBarAlignment.Right,
      100,
    );
    this.item.name = 'RAGX Knowledge';
    this.item.command = 'ragx.openExplorer';
  }

  setVisible(visivel: boolean): void {
    this.visivel = visivel;
    if (!visivel) this.item.hide();
  }

  update(state: SystemState, detalhe?: string): void {
    const r = ROTULOS[state] ?? ROTULOS.disconnected;
    this.item.text = `$(${r.icone}) RAGX: ${r.texto}`;
    // Texto e tooltip, nunca só a cor (§18) — cor sozinha não chega a quem
    // não distingue, e some no tema de alto contraste.
    this.item.tooltip = detalhe ? `${r.dica}\n${detalhe}` : r.dica;
    this.item.backgroundColor =
      state === 'error'
        ? new vscode.ThemeColor('statusBarItem.errorBackground')
        : state === 'outdated' || state === 'warning' || state === 'securityBlocked'
          ? new vscode.ThemeColor('statusBarItem.warningBackground')
          : undefined;
    if (this.visivel) this.item.show();
  }

  dispose(): void {
    this.item.dispose();
  }
}
