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
import {
  ExplorerPanel,
  KnowledgePanel,
  type KnowledgeSurface,
  type PanelHost,
} from './providers/KnowledgePanel';
import { CliRagClient } from './rag/CliClient';
import { discover, toRelPath, type Discovery } from './rag/discovery';
import { McpRagClient } from './rag/McpClient';
import type { RagClient } from './rag/RagClient';
import type { ProjectInfo, SearchMode, SystemState } from './rag/types';
import { Cache } from './services/cache';
import { disposeLogger, log, logError, showLogs } from './services/logger';
import { StatusBar } from './services/statusBar';

let cliente: RagClient | undefined;
let projeto: ProjectInfo | undefined;
let estado: SystemState = 'disconnected';
let descoberta: Discovery = { found: false, markers: [], needsIndex: false };
let painel: KnowledgePanel | undefined;
let hospedeiro: PanelHost | undefined;
let contexto: vscode.ExtensionContext | undefined;
let statusBar: StatusBar | undefined;
let cache: Cache | undefined;

/**
 * Para onde vai um comando de navegação.
 *
 * Com a aba do editor aberta, é lá que a pessoa está olhando — mandar o
 * comando para a barra lateral escondida faria o clique parecer sem efeito.
 */
function superficie(): KnowledgeSurface | undefined {
  // Uma aba já aberta sempre ganha da preferência: é onde a pessoa está.
  if (ExplorerPanel.ativo) return ExplorerPanel.ativo;
  const preferida = vscode.workspace
    .getConfiguration('ragx')
    .get<string>('defaultSurface', 'sidebar');
  if (preferida === 'editor' && contexto && hospedeiro) {
    return ExplorerPanel.abrir(contexto.extensionUri, hospedeiro);
  }
  return painel;
}

function abrirNoEditor(page?: PageId, payload?: Record<string, string>): void {
  if (!contexto || !hospedeiro) return;
  ExplorerPanel.abrir(contexto.extensionUri, hospedeiro, page, payload);
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  log('RAGX Knowledge Explorer ativando');
  contexto = context;

  const cfg = () => vscode.workspace.getConfiguration('ragx');
  cache = new Cache(cfg().get<boolean>('cacheEnabled', true));
  statusBar = new StatusBar();
  statusBar.setVisible(cfg().get<boolean>('statusBar', true));

  // Um único host para as duas superfícies: o que a barra lateral e a aba do
  // editor mostram vem exatamente da mesma fonte, inclusive o cache.
  hospedeiro = {
    client: () => cliente,
    project: () => projeto,
    state: () => estado,
    reconnect: () => conectar(true),
    cache: cache!,
    settings: lerSettings,
    root: () => descoberta.root,
    openEditor: (page?: PageId) => abrirNoEditor(page),
  };
  painel = new KnowledgePanel(context.extensionUri, hospedeiro);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(KnowledgePanel.viewId, painel, {
      // O estado da UI sobrevive a esconder o painel. Sem isto, trocar de aba
      // perde a busca e o contexto que a pessoa acabou de montar.
      webviewOptions: { retainContextWhenHidden: true },
    }),
    // Recarregar a janela não pode fechar a aba: o VS Code a reabre e pede
    // esta função para devolvê-la ao estado de trabalho.
    vscode.window.registerWebviewPanelSerializer(ExplorerPanel.viewType, {
      deserializeWebviewPanel: async (panel) => {
        ExplorerPanel.restaurar(panel, context.extensionUri, hospedeiro!);
      },
    }),
    statusBar,
    { dispose: disposeLogger },
    { dispose: cancelarReconexao },
    { dispose: () => void cliente?.dispose() },
  );

  registrarComandos(context);

  // Reage a mudança de configuração sem exigir recarregar a janela.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (!e.affectsConfiguration('ragx')) return;
      cache?.setEnabled(cfg().get<boolean>('cacheEnabled', true));
      statusBar?.setVisible(cfg().get<boolean>('statusBar', true));
      avisarTodas();
      if (e.affectsConfiguration('ragx.connection') || e.affectsConfiguration('ragx.command')) {
        await conectar(true);
      }
    }),
    // Trocar de pasta só justifica reconectar se a RAIZ do projeto mudou.
    // Adicionar uma pasta de anotações ao workspace derrubava a conexão e
    // pagava o boot do Python de novo, sem nada ter mudado para o RAGX.
    vscode.workspace.onDidChangeWorkspaceFolders(async () => {
      const antes = descoberta.root?.toString();
      const agora = (await discover()).root?.toString();
      if (antes === agora) {
        log('workspace mudou, mas a raiz do projeto é a mesma — conexão mantida');
        return;
      }
      log(`raiz do projeto mudou (${antes ?? 'nenhuma'} -> ${agora ?? 'nenhuma'})`);
      tentativasFalhas = 0;
      await conectar(true);
    }),
  );

  registrarAutoSync(context);
  void conectar(false);
}

export async function deactivate(): Promise<void> {
  // Cancelar ANTES de soltar o cliente: um timer que dispara depois do
  // shutdown sobe um processo Python que ninguém mais vai fechar.
  cancelarReconexao();
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
  avisarTodas(detalhe);
}

/**
 * O estado vai para as DUAS superfícies, sempre.
 *
 * Mandar só para a que está em foco deixaria a outra mostrando "conectando"
 * para sempre — e ela reaparece assim que a pessoa troca de aba.
 */
function avisarTodas(detalhe?: string): void {
  painel?.pushState(detalhe);
  ExplorerPanel.ativo?.pushState(detalhe);
}

/**
 * Reconexão com espera crescente.
 *
 * Um RAGX que não sobe (não instalado, fora do PATH) falha em ~50 ms. Tentar
 * de novo imediatamente vira um laço que consome CPU sem chance nenhuma de
 * sucesso — e com `spawn` de processo a cada volta. A espera dobra até o teto
 * e zera assim que uma conexão dá certo.
 */
const ESPERA_INICIAL_MS = 1_000;
const ESPERA_MAXIMA_MS = 60_000;
const MAX_TENTATIVAS = 6;

let tentativasFalhas = 0;
let timerReconexao: NodeJS.Timeout | undefined;
/** Conexão em andamento. Existe para que duas chamadas não subam DOIS RAGX. */
let conexaoEmCurso: Promise<void> | undefined;

function cancelarReconexao(): void {
  if (timerReconexao) clearTimeout(timerReconexao);
  timerReconexao = undefined;
}

function agendarReconexao(motivo: string): void {
  cancelarReconexao();
  if (tentativasFalhas >= MAX_TENTATIVAS) {
    log(`desisti de reconectar após ${tentativasFalhas} tentativas (${motivo})`);
    mudarEstado('error', `RAGX indisponível: ${motivo}. Use "RAGX: Reconnect".`);
    return;
  }
  const espera = Math.min(ESPERA_INICIAL_MS * 2 ** tentativasFalhas, ESPERA_MAXIMA_MS);
  tentativasFalhas += 1;
  log(`reconectando em ${espera}ms (tentativa ${tentativasFalhas}) — ${motivo}`);
  timerReconexao = setTimeout(() => void conectar(true), espera);
}

/**
 * O processo do RAGX caiu sozinho. Não é o mesmo que uma conexão que falhou:
 * aqui já houve um RAGX funcionando, então vale tentar de novo.
 */
function aoCairOProcesso(motivo: string): void {
  cliente = undefined;
  projeto = undefined;
  mudarEstado('warning', `conexão com o RAGX perdida: ${motivo}`);
  agendarReconexao(motivo);
}

async function conectar(forcar: boolean): Promise<void> {
  if (cliente && !forcar) return;
  // Ativação, troca de pasta e mudança de configuração podem chegar juntas.
  // Sem esta fila, cada uma sobe seu próprio processo Python e só o último
  // fica referenciado — os outros viram processos órfãos de ~100 MB.
  if (conexaoEmCurso) {
    await conexaoEmCurso;
    if (cliente && !forcar) return;
  }
  conexaoEmCurso = conectarAgora();
  try {
    await conexaoEmCurso;
  } finally {
    conexaoEmCurso = undefined;
  }
}

async function conectarAgora(): Promise<void> {
  cancelarReconexao();
  await cliente?.dispose();
  cliente = undefined;
  projeto = undefined;
  cache?.clear();

  const tDescoberta = Date.now();
  descoberta = await discover();
  log(`[RAGX VSCode] Discovering RAGX — ${Date.now() - tDescoberta}ms`);
  if (!descoberta.found || !descoberta.root) {
    log('nenhum projeto RAGX encontrado no workspace');
    // Não há o que reconectar: sem projeto, tentar de novo não muda nada.
    tentativasFalhas = 0;
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
          onCrash: aoCairOProcesso,
        }),
    );
  }
  if (modo === 'cli' || modo === 'auto') {
    tentativas.push(() => new CliRagClient({ command: comando, cwd, log }));
  }

  const t0 = Date.now();
  for (const criar of tentativas) {
    const candidato = criar();
    const r = await candidato.connect();
    if (r.ok && r.data) {
      cliente = candidato;
      projeto = r.data;
      tentativasFalhas = 0;
      log(`[RAGX VSCode] Ready — por ${r.data.transport} em ${Date.now() - t0}ms`);
      mudarEstado(descoberta.needsIndex ? 'outdated' : 'ready');
      return;
    }
    await candidato.dispose();
    log(`transporte ${candidato.transport} falhou: ${r.error?.message}`);
  }

  mudarEstado('error', 'não foi possível conectar ao RAGX — veja os logs');
  agendarReconexao('nenhum transporte respondeu');
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
    superficie()?.navigate(page, payload);

  const comandos: Array<[string, (...args: unknown[]) => unknown]> = [
    ['ragx.openExplorer', ir('overview')],
    ['ragx.openInEditor', () => abrirNoEditor()],
    ['ragx.search', abrirBusca],
    ['ragx.buildContext', ir('context')],
    ['ragx.exploreGraph', ir('graph')],
    ['ragx.openDictionary', ir('dictionary')],
    ['ragx.openTasks', ir('tasks')],
    ['ragx.analyzeRequest', analisarPedido],
    ['ragx.openAgents', ir('agents')],
    ['ragx.status', ir('overview')],
    ['ragx.securityScan', ir('security')],
    ['ragx.sync', sincronizar],
    ['ragx.reconnect', reconectarAgora],
    ['ragx.showLogs', showLogs],
    ['ragx.knowledgeForFile', conhecimentoDoArquivo],
    ['ragx.trainAgent', () => avisarNaoDisponivel('Train Agent')],
    ['ragx.evaluateAgent', () => avisarNaoDisponivel('Agent Evaluation')],
  ];

  for (const [id, handler] of comandos) {
    context.subscriptions.push(vscode.commands.registerCommand(id, handler));
  }
}

/**
 * "Reconnect" do menu. Zera o contador de falhas porque é um pedido
 * explícito: se a pessoa acabou de instalar o RAGX, fazê-la esperar o próximo
 * passo do backoff (até um minuto) pareceria que o comando não funcionou.
 */
async function reconectarAgora(): Promise<void> {
  tentativasFalhas = 0;
  cancelarReconexao();
  await conectar(true);
}

async function abrirBusca(): Promise<void> {
  const consulta = await vscode.window.showInputBox({
    prompt: 'Buscar no conhecimento do RAGX',
    placeHolder: 'como funciona a autenticação?',
    ignoreFocusOut: true,
  });
  if (consulta === undefined) return;
  superficie()?.navigate('search', { query: consulta });
}

/**
 * Classifica um pedido antes de começar a escrever código.
 *
 * O Task Analyzer é a parte do RAGX que decide entre "faça agora" e
 * "documente e decomponha antes". Ele só LÊ: nada é criado até alguém rodar
 * `ragx task plan --apply`, que é escrita e continua fora do plugin.
 */
async function analisarPedido(): Promise<void> {
  const pedido = await vscode.window.showInputBox({
    prompt: 'O que você quer fazer? O RAGX classifica antes de você começar.',
    placeHolder: 'migrar a autenticação para SSO em todos os serviços',
    ignoreFocusOut: true,
  });
  if (!pedido?.trim()) return;
  superficie()?.navigate('tasks', { request: pedido.trim() });
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
  avisarTodas();
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
  superficie()?.navigate('documents', { path: rel });
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
