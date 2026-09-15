/**
 * A mesma UI em dois lugares: a barra lateral e o editor.
 *
 * A lateral é onde o VS Code coloca o que fica sempre à mão — e tem ~300px.
 * Grafo, DAG de tarefas e comparação de resultados não cabem ali. Por isso a
 * mesma webview também abre como aba do editor, onde ocupa a janela inteira.
 *
 * As duas hospedagens compartilham TUDO que importa (o roteador de mensagens e
 * o HTML): a diferença é só onde o VS Code desenha. Sem isso, cada correção
 * precisaria ser feita duas vezes — e seria esquecida uma vez.
 */

import * as vscode from 'vscode';

import type { PageId, WebviewMessage } from '../protocol';
import {
  localResourceRoots,
  MessageRouter,
  renderHtml,
  type PanelHost,
} from './router';

export type { PanelHost } from './router';

/** O que a extensão pode pedir a qualquer das duas superfícies. */
export interface KnowledgeSurface {
  reveal(): void;
  navigate(page: PageId, payload?: Record<string, string>): void;
  pushState(message?: string): void;
}

// ── barra lateral ───────────────────────────────────────────────────────
export class KnowledgePanel implements vscode.WebviewViewProvider, KnowledgeSurface {
  static readonly viewId = 'ragx.explorer';

  private view?: vscode.WebviewView;
  private router?: MessageRouter;

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly host: PanelHost,
  ) {}

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: localResourceRoots(this.extensionUri),
    };
    view.webview.html = renderHtml(view.webview, this.extensionUri, 'sidebar');

    const router = new MessageRouter(
      this.host,
      (msg) => void view.webview.postMessage(msg),
      'sidebar',
    );
    this.router?.dispose();
    this.router = router;

    view.webview.onDidReceiveMessage((m: WebviewMessage) => void router.handle(m));
    view.onDidChangeVisibility(() => {
      if (view.visible) router.pushState();
    });
    view.onDidDispose(() => {
      router.dispose();
      if (this.router === router) this.router = undefined;
      this.view = undefined;
    });

    router.pushState();
  }

  reveal(): void {
    if (this.view) {
      this.view.show?.(true);
    } else {
      void vscode.commands.executeCommand('ragx.explorer.focus');
    }
  }

  navigate(page: PageId, payload?: Record<string, string>): void {
    this.reveal();
    void this.view?.webview.postMessage({ type: 'navigate', page, payload });
  }

  pushState(message?: string): void {
    this.router?.pushState(message);
  }

  dispose(): void {
    this.router?.dispose();
  }
}

// ── aba do editor (tela cheia) ──────────────────────────────────────────
export class ExplorerPanel implements KnowledgeSurface {
  static readonly viewType = 'ragx.explorerPanel';
  /** Uma aba só. Abrir a segunda foca a primeira em vez de duplicar estado. */
  private static atual?: ExplorerPanel;

  /** A aba aberta, se houver. É para ela que a navegação vai quando existe. */
  static get ativo(): ExplorerPanel | undefined {
    return ExplorerPanel.atual;
  }

  static abrir(
    extensionUri: vscode.Uri,
    host: PanelHost,
    page?: PageId,
    payload?: Record<string, string>,
  ): ExplorerPanel {
    if (ExplorerPanel.atual) {
      ExplorerPanel.atual.panel.reveal(undefined, false);
      if (page) ExplorerPanel.atual.navigate(page, payload);
      return ExplorerPanel.atual;
    }

    const panel = vscode.window.createWebviewPanel(
      ExplorerPanel.viewType,
      'RAGX Knowledge',
      // A coluna ATIVA, não a primeira: abrir por cima do arquivo que a pessoa
      // está lendo é o tipo de gentileza que ninguém pediu.
      vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One,
      {
        enableScripts: true,
        localResourceRoots: localResourceRoots(extensionUri),
        // Sem isto, trocar de aba destrói a webview e a pessoa perde a busca, o
        // contexto montado e a posição do grafo.
        retainContextWhenHidden: true,
      },
    );
    const criado = new ExplorerPanel(panel, extensionUri, host);
    if (page) criado.navigate(page, payload);
    return criado;
  }

  /** Reabre a aba depois de recarregar a janela (§ estado persistente). */
  static restaurar(
    panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    host: PanelHost,
  ): void {
    panel.webview.options = {
      enableScripts: true,
      localResourceRoots: localResourceRoots(extensionUri),
    };
    new ExplorerPanel(panel, extensionUri, host);
  }

  private readonly router: MessageRouter;

  private constructor(
    private readonly panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    host: PanelHost,
  ) {
    ExplorerPanel.atual = this;
    panel.iconPath = {
      light: vscode.Uri.joinPath(extensionUri, 'media', 'activity.svg'),
      dark: vscode.Uri.joinPath(extensionUri, 'media', 'activity.svg'),
    };
    panel.webview.html = renderHtml(panel.webview, extensionUri, 'editor');

    this.router = new MessageRouter(
      host,
      (msg) => void panel.webview.postMessage(msg),
      'editor',
    );

    panel.webview.onDidReceiveMessage((m: WebviewMessage) => void this.router.handle(m));
    panel.onDidChangeViewState(() => {
      if (panel.visible) this.router.pushState();
    });
    panel.onDidDispose(() => {
      this.router.dispose();
      if (ExplorerPanel.atual === this) ExplorerPanel.atual = undefined;
    });

    this.router.pushState();
  }

  reveal(): void {
    this.panel.reveal(undefined, false);
  }

  navigate(page: PageId, payload?: Record<string, string>): void {
    this.reveal();
    void this.panel.webview.postMessage({ type: 'navigate', page, payload });
  }

  pushState(message?: string): void {
    this.router.pushState(message);
  }

  dispose(): void {
    this.panel.dispose();
  }
}
