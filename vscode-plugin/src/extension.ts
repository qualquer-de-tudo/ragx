/**
 * Ativação, conexão e comandos.
 *
 * A extensão nunca bloqueia o VS Code: a conexão acontece em segundo plano e a
 * UI mostra `connecting` enquanto isso. Subir o processo do RAGX leva alguns
 * segundos na primeira vez (carga do modelo de embeddings), e travar a janela
 * por isso seria imperdoável.
 */

import * as vscode from 'vscode';

import type { PageId, UiSettings } from './protocol';
import { CliRagClient } from './rag/CliClient';
import { discover, toRelPath, type Discovery } from './rag/discovery';
import { McpRagClient } from './rag/McpClient';
import type { RagClient } from './rag/RagClient';
import type { ProjectInfo, SearchMode, SystemState } from './rag/types';
import { KnowledgePanel } from './providers/KnowledgePanel';
import { Cache } from './services/cache';
import { disposeLogger, log, logError, showLogs } from './services/logger';
import { StatusBar } from './services/statusBar';

let cliente: RagClient | undefined;
let projeto: ProjectInfo | undefined;
let estado: SystemState = 'disconnected';
let descoberta: Discovery = { found: false, markers: [], needsIndex: false };
let painel: KnowledgePanel | undefined;
let statusBar: StatusBar | undefined;
let cache: Cache | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  log('RAGX Knowledge Explorer ativando');

  const cfg = () => vscode.workspace.getConfiguration('ragx');
  cache = new Cache(cfg().get<boolean>('cacheEnabled', true));
  statusBar = new StatusBar();
  statusBar.setVisible(cfg().get<boolean>('statusBar', true));

  painel = new KnowledgePanel(context.extensionUri, {
    client: () => cliente,
    project: () => projeto,
    state: () => estado,
    reconnect: () => conectar(true),
    cache: cache!,
    settings: lerSettings,
    root: () => descoberta.root,
  });

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(KnowledgePanel.viewId, painel, {
      // O estado da UI sobrevive a esconder o painel. Sem isto, trocar de aba
      // perde a busca e o contexto que a pessoa acabou de montar.
      webviewOptions: { retainContextWhenHidden: true },
    }),
    statusBar,
    { dispose: disposeLogger },
    { dispose: () => void cliente?.dispose() },
  );

  registrarComandos(context);

  // Reage a mudança de configuração sem exigir recarregar a janela.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (!e.affectsConfiguration('ragx')) return;
      cache?.setEnabled(cfg().get<boolean>('cacheEnabled', true));
      statusBar?.setVisible(cfg().get<boolean>('statusBar', true));
      painel?.pushState();
      if (e.affectsConfiguration('ragx.connection') || e.affectsConfiguration('ragx.command')) {
        await conectar(true);
      }
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(() => void conectar(true)),
  );

  registrarAutoSync(context);
  void conectar(false);
}

export async function deactivate(): Promise<void> {
  await cliente?.dispose();
  cliente = undefined;
}

// ── conexão ─────────────────────────────────────────────────────────────
function mudarEstado(novo: SystemState, detalhe?: string): void {
  estado = novo;
  statusBar?.update(novo, detalhe);
  void vscode.commands.executeCommand(
    'setContext', 'ragx.connected', novo !== 'disconnected' && novo !== 'error',
  );
  painel?.pushState(detalhe);
}

async function conectar(forcar: boolean): Promise<void> {
  if (cliente && !forcar) return;
  await cliente?.dispose();
  cliente = undefined;
  projeto = undefined;
  cache?.clear();

  descoberta = await discover();
  if (!descoberta.found || !descoberta.root) {
    log('nenhum projeto RAGX encontrado no workspace');
    mudarEstado('disconnected', 'nenhum projeto RAGX neste workspace');
    return;
  }
  log(`projeto detectado: ${descoberta.root.fsPath} (${descoberta.markers.join(', ')})`);
  mudarEstado('syncing', 'conectando ao RAGX…');

  const cfg = vscode.workspace.getConfiguration('ragx');
  const comando = cfg.get<string>('command', 'ragx');
  const modo = cfg.get<string>('connection', 'auto');
  const cwd = descoberta.root.fsPath;

  const tentativas: Array<() => RagClient> = [];
  if (modo === 'mcp' || modo === 'auto') {
    tentativas.push(
      () =>
        new McpRagClient({
          command: comando,
          args: cfg.get<string[]>('mcpArgs', ['mcp', 'serve']),
          cwd,
          write: false,
          log,
        }),
    );
  }
  if (modo === 'cli' || modo === 'auto') {
    tentativas.push(() => new CliRagClient({ command: comando, cwd, log }));
  }

  for (const criar of tentativas) {
    const candidato = criar();
    const r = await candidato.connect();
    if (r.ok && r.data) {
      cliente = candidato;
      projeto = r.data;
      log(`conectado por ${r.data.transport}`);
      mudarEstado(descoberta.needsIndex ? 'outdated' : 'ready');
      return;
    }
    await candidato.dispose();
    log(`transporte ${candidato.transport} falhou: ${r.error?.message}`);
  }

  mudarEstado('error', 'não foi possível conectar ao RAGX — veja os logs');
}

function lerSettings(): UiSettings {
  const cfg = vscode.workspace.getConfiguration('ragx');
  return {
    searchMode: cfg.get<SearchMode>('searchMode', 'hybrid'),
    graphMaxDepth: cfg.get<number>('graphMaxDepth', 2),
    maxVisibleNodes: cfg.get<number>('maxVisibleNodes', 120),
    contextTokenBudget: cfg.get<number>('contextTokenBudget', 4000),
  };
}

// ── comandos ────────────────────────────────────────────────────────────
function registrarComandos(context: vscode.ExtensionContext): void {
  const ir = (page: PageId, payload?: Record<string, string>) => () =>
    painel?.navigate(page, payload);

  const comandos: Array<[string, (...args: unknown[]) => unknown]> = [
    ['ragx.openExplorer', ir('overview')],
    ['ragx.search', abrirBusca],
    ['ragx.buildContext', ir('context')],
    ['ragx.exploreGraph', ir('graph')],
    ['ragx.openDictionary', ir('dictionary')],
    ['ragx.openAgents', ir('agents')],
    ['ragx.status', ir('overview')],
    ['ragx.securityScan', ir('security')],
    ['ragx.sync', sincronizar],
    ['ragx.reconnect', () => conectar(true)],
    ['ragx.showLogs', showLogs],
    ['ragx.knowledgeForFile', conhecimentoDoArquivo],
    ['ragx.trainAgent', () => avisarNaoDisponivel('Train Agent')],
    ['ragx.evaluateAgent', () => avisarNaoDisponivel('Agent Evaluation')],
  ];

  for (const [id, handler] of comandos) {
    context.subscriptions.push(vscode.commands.registerCommand(id, handler));
  }
}

async function abrirBusca(): Promise<void> {
  const consulta = await vscode.window.showInputBox({
    prompt: 'Buscar no conhecimento do RAGX',
    placeHolder: 'como funciona a autenticação?',
    ignoreFocusOut: true,
  });
  if (consulta === undefined) return;
  painel?.navigate('search', { query: consulta });
}

async function sincronizar(): Promise<void> {
  if (!cliente) {
    void vscode.window.showWarningMessage('RAGX não conectado.');
    return;
  }
  const anterior = estado;
  mudarEstado('syncing');
  const r = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: 'RAGX: sincronizando…' },
    () => cliente!.sync(),
  );
  cache?.bumpVersion(String(Date.now()));
  if (r.ok) {
    mudarEstado('ready');
    void vscode.window.showInformationMessage(
      `Conhecimento sincronizado — ${r.data?.indexed ?? 0} documento(s) atualizado(s)`,
    );
  } else {
    mudarEstado(anterior);
    void vscode.window
      .showErrorMessage(`RAGX: falha ao sincronizar. ${r.error?.message ?? ''}`, 'Ver logs')
      .then((escolha) => escolha === 'Ver logs' && showLogs());
  }
  painel?.pushState();
}

/** Código → conhecimento (§15). */
async function conhecimentoDoArquivo(): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor || !descoberta.root) {
    void vscode.window.showWarningMessage('Abra um arquivo do projeto primeiro.');
    return;
  }
  const rel = toRelPath(descoberta.root, editor.document.uri);
  if (!rel) {
    void vscode.window.showWarningMessage(
      'Este arquivo está fora da raiz do projeto RAGX.',
    );
    return;
  }
  painel?.navigate('documents', { path: rel });
}

function avisarNaoDisponivel(nome: string): void {
  // Dizer que não está pronto é melhor que abrir uma tela vazia. O MVP (§54)
  // deixou o treino avançado para depois, de propósito.
  void vscode.window
    .showInformationMessage(
      `${nome} ainda não está no plugin. Use a CLI: \`ragx agent --help\`.`,
      'Ver comandos',
    )
    .then((escolha) => {
      if (escolha === 'Ver comandos') {
        void vscode.commands.executeCommand('workbench.action.terminal.new');
      }
    });
}

// ── auto sync ───────────────────────────────────────────────────────────
function registrarAutoSync(context: vscode.ExtensionContext): void {
  let timer: NodeJS.Timeout | undefined;

  const agendar = () => {
    // Debounce: salvar doze arquivos em sequência vira UM sync, não doze.
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void sincronizarSilencioso(), 2500);
  };

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const modo = vscode.workspace.getConfiguration('ragx').get<string>('autoSync', 'off');
      if (modo !== 'onSave' || !cliente || !descoberta.root) return;
      if (!toRelPath(descoberta.root, doc.uri)) return;
      agendar();
    }),
    { dispose: () => timer && clearTimeout(timer) },
  );
}

async function sincronizarSilencioso(): Promise<void> {
  if (!cliente) return;
  try {
    mudarEstado('syncing');
    const r = await cliente.sync();
    cache?.bumpVersion(String(Date.now()));
    mudarEstado(r.ok ? 'ready' : 'warning', r.ok ? undefined : r.error?.message);
    // Sem notificação: auto sync que avisa a cada save vira ruído (§28).
    log(`auto sync — ${r.ok ? `${r.data?.indexed ?? 0} documento(s)` : r.error?.message}`);
  } catch (err) {
    logError('autoSync', err);
    mudarEstado('warning', 'auto sync falhou — veja os logs');
  }
}
