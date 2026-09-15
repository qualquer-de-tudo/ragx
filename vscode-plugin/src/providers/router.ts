/**
 * O roteador de mensagens, compartilhado pelas duas hospedagens da UI.
 *
 * A mesma interface roda em dois lugares: a barra lateral (estreita, sempre à
 * mão) e um painel no editor (largo, maximizável). Duplicar o tratamento de
 * mensagens entre os dois garantiria que uma correção fosse aplicada em um e
 * esquecida no outro — então ele vive aqui, e cada hospedagem só fornece o
 * `Webview`.
 */

import * as vscode from 'vscode';

import type {
  ExtensionMessage,
  HostMode,
  PageId,
  ResultPayload,
  UiSettings,
  WebviewMessage,
} from '../protocol';
import { humanize, type RagClient } from '../rag/RagClient';
import type { ProjectInfo, RagResult, SystemState } from '../rag/types';
import { dropBlocked, safeRelPath } from '../security/guard';
import type { Cache } from '../services/cache';
import { log, logError, showLogs } from '../services/logger';

export interface PanelHost {
  client(): RagClient | undefined;
  project(): ProjectInfo | undefined;
  state(): SystemState;
  reconnect(): Promise<void>;
  cache: Cache;
  settings(): UiSettings;
  root(): vscode.Uri | undefined;
  /** Abre a mesma UI no editor, em largura cheia. */
  openEditor(page?: PageId): void;
}

export class MessageRouter {
  private emAndamento = new Map<string, AbortController>();

  constructor(
    private readonly host: PanelHost,
    private readonly post: (msg: ExtensionMessage) => void,
    /** Onde esta webview está: a UI se adapta, e só a lateral oferece "tela cheia". */
    private readonly modo: HostMode,
  ) {}

  dispose(): void {
    this.abortAll();
  }

  pushState(message?: string): void {
    this.post({
      type: 'state',
      state: this.host.state(),
      project: this.host.project(),
      message,
      host: this.modo,
    });
    this.post({ type: 'settings', settings: this.host.settings() });
  }

  private ok(id: string, payload: ResultPayload): void {
    this.post({ type: 'result', id, ok: true, payload });
  }

  private erro(id: string, code: string, message: string): void {
    const h = humanize({ code, message });
    this.post({
      type: 'result',
      id,
      ok: false,
      error: { code, title: h.title, reason: h.reason, actions: h.actions },
    });
  }

  /** Desempacota `RagResult` numa resposta do protocolo. */
  private reply<T>(
    id: string,
    r: RagResult<T>,
    toPayload: (data: T) => ResultPayload,
  ): void {
    if (!r.ok || r.data === undefined) {
      this.erro(id, r.error?.code ?? 'error', r.error?.message ?? 'falha sem detalhe');
      return;
    }
    this.ok(id, toPayload(r.data));
  }

  private abortAll(): void {
    for (const c of this.emAndamento.values()) c.abort();
    this.emAndamento.clear();
  }

  async handle(msg: WebviewMessage): Promise<void> {
    const cliente = this.host.client();
    const semCliente = ['ready', 'reconnect', 'openLogs', 'openSettings', 'openEditor'];
    if (!cliente && !semCliente.includes(msg.type)) {
      this.erro(msg.id, 'disconnected', 'RAGX não conectado');
      return;
    }

    try {
      switch (msg.type) {
        case 'ready':
          this.pushState();
          this.ok(msg.id, { kind: 'ack' });
          return;

        case 'openEditor':
          this.host.openEditor(msg.page);
          this.ok(msg.id, { kind: 'ack' });
          return;

        case 'search': {
          // Cancela a busca anterior: sem isso, digitar rápido deixa três
          // consultas correndo e a mais lenta vence.
          this.abortAll();
          const controller = new AbortController();
          this.emAndamento.set(msg.id, controller);
          const r = await cliente!.search(
            msg.query, msg.mode, msg.limit, msg.filters, controller.signal,
          );
          this.emAndamento.delete(msg.id);
          if (controller.signal.aborted) return;
          if (r.ok && r.data) {
            const { kept, removed } = dropBlocked(r.data.results);
            if (removed) log(`${removed} resultado(s) omitido(s) por marcação de bloqueio`);
            r.data.results = kept;
          }
          this.reply(msg.id, r, (response) => ({ kind: 'search', response }));
          return;
        }

        case 'cancelSearch':
          this.abortAll();
          this.ok(msg.id, { kind: 'ack' });
          return;

        // ── orquestração (§13) ────────────────────────────────────────
        case 'getTasks':
          this.reply(msg.id, await cliente!.tasks(msg.project, msg.status), (tasks) => ({
            kind: 'tasks', tasks,
          }));
          return;

        case 'getTask':
          this.reply(msg.id, await cliente!.task(msg.taskId), (task) => ({
            kind: 'task', task,
          }));
          return;

        case 'getTaskGraph':
          this.reply(msg.id, await cliente!.taskGraph(msg.project), (graph) => ({
            kind: 'taskGraph', graph,
          }));
          return;

        case 'getTaskPanel':
          this.reply(msg.id, await cliente!.taskPanel(), (panel) => ({
            kind: 'taskPanel', panel,
          }));
          return;

        case 'analyzeRequest':
          this.reply(msg.id, await cliente!.analyzeRequest(msg.request), (analysis) => ({
            kind: 'analysis', analysis,
          }));
          return;

        case 'getStats': {
          const cacheado = this.host.cache.get('stats', 'default');
          if (cacheado) {
            this.ok(msg.id, { kind: 'stats', stats: cacheado as never });
            return;
          }
          const r = await cliente!.stats();
          if (r.ok && r.data) this.host.cache.set('stats', 'default', r.data, 15_000);
          this.reply(msg.id, r, (stats) => ({ kind: 'stats', stats }));
          return;
        }

        case 'getHealth':
          this.reply(msg.id, await cliente!.health(), (checks) => ({ kind: 'health', checks }));
          return;

        case 'getGraph': {
          const chave = `${msg.entity}:${msg.depth}`;
          const cacheado = this.host.cache.get('graph', chave);
          if (cacheado) {
            this.ok(msg.id, { kind: 'graph', graph: cacheado as never });
            return;
          }
          const r = await cliente!.graph(
            msg.entity, msg.depth, this.host.settings().maxVisibleNodes,
          );
          if (r.ok && r.data) this.host.cache.set('graph', chave, r.data);
          this.reply(msg.id, r, (graph) => ({ kind: 'graph', graph }));
          return;
        }

        case 'getEntity':
          this.reply(msg.id, await cliente!.entity(msg.name), (entity) => ({
            kind: 'entity', entity,
          }));
          return;

        case 'getDictionary': {
          const cacheado = this.host.cache.get('dictionary', 'default');
          if (cacheado) {
            this.ok(msg.id, { kind: 'dictionary', sections: cacheado as never });
            return;
          }
          const r = await cliente!.dictionary();
          if (r.ok && r.data) this.host.cache.set('dictionary', 'default', r.data, 300_000);
          this.reply(msg.id, r, (sections) => ({ kind: 'dictionary', sections }));
          return;
        }

        case 'getDocuments':
          this.reply(msg.id, await cliente!.documents(msg.query), (documents) => ({
            kind: 'documents', documents,
          }));
          return;

        case 'getFileKnowledge':
          this.reply(msg.id, await cliente!.fileKnowledge(msg.path), (knowledge) => ({
            kind: 'fileKnowledge', knowledge,
          }));
          return;

        case 'getChunk':
          this.reply(msg.id, await cliente!.chunk(msg.chunkId), (chunk) => ({
            kind: 'chunk', chunk,
          }));
          return;

        case 'buildContext':
          this.reply(msg.id, await cliente!.buildContext(msg.query, msg.tokens), (pack) => ({
            kind: 'context', pack,
          }));
          return;

        case 'getSecurity':
          this.reply(msg.id, await cliente!.security(), (security) => ({
            kind: 'security', security,
          }));
          return;

        case 'getMonitor':
          this.reply(msg.id, await cliente!.monitor(), (monitor) => ({
            kind: 'monitor', monitor,
          }));
          return;

        case 'getAgents':
          this.reply(msg.id, await cliente!.agents(), (agents) => ({ kind: 'agents', agents }));
          return;

        case 'getSources': {
          const cacheado = this.host.cache.get('sources', 'default');
          if (cacheado) {
            this.ok(msg.id, { kind: 'sources', overview: cacheado as never });
            return;
          }
          const r = await cliente!.sources();
          if (r.ok && r.data) this.host.cache.set('sources', 'default', r.data, 30_000);
          this.reply(msg.id, r, (overview) => ({ kind: 'sources', overview }));
          return;
        }

        case 'sync': {
          const r = await vscode.window.withProgress(
            { location: vscode.ProgressLocation.Notification, title: 'RAGX: sincronizando…' },
            () => cliente!.sync(),
          );
          if (r.ok) {
            this.host.cache.bumpVersion(String(Date.now()));
            // Uma notificação com o resumo, não uma por arquivo (§28).
            void vscode.window.showInformationMessage(
              `Conhecimento sincronizado — ${r.data?.indexed ?? 0} documento(s)` +
                (r.data?.warnings.length ? `, ${r.data.warnings.length} aviso(s)` : ''),
            );
          }
          this.reply(msg.id, r, (d) => ({
            kind: 'sync', indexed: d.indexed, removed: d.removed, warnings: d.warnings,
          }));
          return;
        }

        case 'reconnect':
          await this.host.reconnect();
          this.pushState();
          this.ok(msg.id, { kind: 'ack' });
          return;

        case 'openFile':
          await this.openFile(msg.path, msg.line, msg.endLine);
          this.ok(msg.id, { kind: 'ack' });
          return;

        case 'copy':
          await vscode.env.clipboard.writeText(msg.text);
          void vscode.window.setStatusBarMessage('$(check) Copiado', 2000);
          this.ok(msg.id, { kind: 'ack' });
          return;

        case 'saveContext': {
          const doc = await vscode.workspace.openTextDocument({
            content: msg.markdown,
            language: 'markdown',
          });
          await vscode.window.showTextDocument(doc, { preview: false });
          this.ok(msg.id, { kind: 'ack' });
          return;
        }

        case 'openLogs':
          showLogs();
          this.ok(msg.id, { kind: 'ack' });
          return;

        case 'openSettings':
          await vscode.commands.executeCommand(
            'workbench.action.openSettings', '@ext:ragx.ragx-knowledge-explorer',
          );
          this.ok(msg.id, { kind: 'ack' });
          return;

        case 'runCommand':
          await vscode.commands.executeCommand(msg.command);
          this.ok(msg.id, { kind: 'ack' });
          return;
      }
    } catch (err) {
      logError(msg.type, err);
      this.erro(msg.id, 'internal', 'falha interna — veja os logs');
    }
  }

  /** Conhecimento → fonte (§16): abre o arquivo e leva o cursor à linha. */
  private async openFile(caminho: string, linha?: number, fim?: number): Promise<void> {
    const rel = safeRelPath(caminho);
    const raiz = this.host.root();
    if (!rel || !raiz) {
      void vscode.window.showWarningMessage(`Caminho inválido: ${caminho}`);
      return;
    }
    if (rel.startsWith('@base/')) {
      void vscode.window.showInformationMessage(
        'Este conhecimento vem de uma fonte base compartilhada, fora do ' +
          'repositório. Use `ragx base list` para ver onde ela está instalada.',
      );
      return;
    }
    const uri = vscode.Uri.joinPath(raiz, ...rel.split('/'));
    try {
      const doc = await vscode.workspace.openTextDocument(uri);
      const editor = await vscode.window.showTextDocument(doc, {
        preview: true,
        // Ao lado, não por cima: com o painel ocupando o editor, abrir o
        // arquivo na mesma coluna esconderia a UI que originou o clique.
        viewColumn: vscode.ViewColumn.Beside,
      });
      if (linha && linha > 0) {
        const inicio = new vscode.Position(Math.max(0, linha - 1), 0);
        const termino = new vscode.Position(Math.max(0, (fim ?? linha) - 1), 0);
        editor.selection = new vscode.Selection(inicio, inicio);
        editor.revealRange(
          new vscode.Range(inicio, termino),
          vscode.TextEditorRevealType.InCenterIfOutsideViewport,
        );
      }
    } catch {
      // O índice pode estar à frente do disco — o arquivo foi removido depois
      // de indexado. Dizer isso é mais útil que um erro genérico.
      void vscode.window.showWarningMessage(
        `Não foi possível abrir ${rel}. O índice pode estar à frente do ` +
          `working tree — rode Sync.`,
      );
    }
  }
}

/**
 * HTML da webview, com CSP restrita (§34).
 *
 * `script-src` só com nonce, `connect-src 'none'` porque a webview NUNCA fala
 * com a rede — todo dado chega por postMessage. Sem `unsafe-eval`, sem
 * `unsafe-inline` em script.
 */
export function renderHtml(
  webview: vscode.Webview,
  extensionUri: vscode.Uri,
  modo: 'sidebar' | 'editor',
): string {
  const base = vscode.Uri.joinPath(extensionUri, 'dist', 'webview');
  const script = webview.asWebviewUri(vscode.Uri.joinPath(base, 'index.js'));
  const estilo = webview.asWebviewUri(vscode.Uri.joinPath(base, 'index.css'));
  const nonce = criarNonce();

  const csp = [
    "default-src 'none'",
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `script-src 'nonce-${nonce}'`,
    `font-src ${webview.cspSource}`,
    "connect-src 'none'",
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
  ].join('; ');

  return `<!DOCTYPE html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="Content-Security-Policy" content="${csp}" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link href="${estilo}" rel="stylesheet" />
    <title>RAGX Knowledge</title>
  </head>
  <body data-modo="${modo}">
    <div id="root"></div>
    <script nonce="${nonce}" src="${script}"></script>
  </body>
</html>`;
}

function criarNonce(): string {
  const alfabeto = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let out = '';
  for (let i = 0; i < 32; i++) {
    out += alfabeto.charAt(Math.floor(Math.random() * alfabeto.length));
  }
  return out;
}

export function localResourceRoots(extensionUri: vscode.Uri): vscode.Uri[] {
  // Só a pasta de build. Sem isto, a webview poderia carregar qualquer coisa
  // do disco — e "qualquer coisa" inclui o que o gate bloqueou.
  return [vscode.Uri.joinPath(extensionUri, 'dist', 'webview')];
}
