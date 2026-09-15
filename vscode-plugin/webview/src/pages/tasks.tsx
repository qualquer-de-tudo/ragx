/**
 * Tarefas — o que o RAGX decompôs, em que estado está, e o que trava o quê.
 *
 * A Fase 13 do RAGX já existia inteira no MCP e na CLI sem nenhuma superfície
 * visual: dava para o agente pegar trabalho, mas não para uma pessoa ver o
 * plano. Esta tela é LEITURA. Reivindicar, reportar resultado e mudar estado
 * continuam na CLI e no agente — uma tela de exploração que também executa
 * trabalho daria ao plugin um poder que o servidor sobe desligado.
 */

import { useEffect, useState } from 'react';

import type {
  RequestAnalysis,
  TaskDetail,
  TaskGraph,
  TaskInfo,
  TaskPanel,
} from '../../../src/rag/types';
import { request, send } from '../bridge';
import {
  Badge,
  Bar,
  Button,
  Card,
  EmptyState,
  Grade,
  Input,
  Metric,
  Split,
  fmt,
} from '../components';
import { Quadro, usePedido } from './estado';

/** Cor por estado. O texto continua sendo a informação; a cor só acelera (§18). */
const TOM: Record<string, 'ok' | 'warn' | 'err' | 'info' | 'neutral'> = {
  completed: 'ok',
  running: 'info',
  ready: 'info',
  queued: 'info',
  pending: 'neutral',
  blocked: 'warn',
  needs_review: 'warn',
  failed: 'err',
  cancelled: 'neutral',
};

const ORDEM = [
  'running', 'ready', 'queued', 'blocked', 'needs_review',
  'pending', 'failed', 'completed', 'cancelled',
];

export function Tasks({
  amplo,
  pedidoInicial,
}: {
  amplo: boolean;
  /** Pedido vindo do comando "Analyze Request". */
  pedidoInicial?: string;
}) {
  const [filtro, setFiltro] = useState<string>();
  const [selecionada, setSelecionada] = useState<string>();
  const [verGrafo, setVerGrafo] = useState(false);

  const [painel, recarregarPainel] = usePedido<TaskPanel>(
    () => request({ type: 'getTaskPanel' }, 'taskPanel').then((r) => r.panel),
    [],
  );
  const [lista, recarregarLista] = usePedido<TaskInfo[]>(
    () => request({ type: 'getTasks', status: filtro }, 'tasks').then((r) => r.tasks),
    [filtro],
  );
  const [detalhe, recarregarDetalhe] = usePedido<TaskDetail>(
    () => request({ type: 'getTask', taskId: selecionada! }, 'task').then((r) => r.task),
    [selecionada],
    Boolean(selecionada),
  );

  const semOrquestracao =
    painel.fase === 'ready' &&
    Boolean(painel.dado.unavailable) &&
    !Object.keys(painel.dado.counts).length;

  return (
    <div className="space-y-3">
      <Analisador inicial={pedidoInicial} />

      <Quadro estado={painel} onRetry={recarregarPainel}>
        {(p) =>
          semOrquestracao ? (
            <EmptyState
              title="Nenhum plano de trabalho ainda"
              hints={[
                'O RAGX classifica um pedido e, quando ele é grande, decompõe em tarefas.',
                'Analise um pedido acima para ver o veredito — isso não cria nada.',
                'Para aplicar o plano: `ragx task plan "..." --apply`.',
              ]}
            />
          ) : (
            <>
              <Card
                title="Painel"
                action={
                  <Button variant="ghost" onClick={recarregarPainel}>
                    Atualizar
                  </Button>
                }
              >
                <div className="flex flex-wrap gap-1.5 mb-2">
                  <Chip ativo={!filtro} onClick={() => setFiltro(undefined)}>
                    todas {fmt(Object.values(p.counts).reduce((a, b) => a + b, 0))}
                  </Chip>
                  {ORDEM.filter((e) => p.counts[e]).map((e) => (
                    <Chip key={e} ativo={filtro === e} onClick={() => setFiltro(e)}>
                      <Badge tone={TOM[e] ?? 'neutral'}>{e}</Badge> {fmt(p.counts[e])}
                    </Chip>
                  ))}
                </div>
                {p.projects.length > 0 && (
                  <Metric label="Projetos de trabalho" value={p.projects.length} />
                )}
                {p.scheduler && (
                  <>
                    <Metric
                      label="Agendamentos"
                      value={`${p.scheduler.enabled}/${p.scheduler.total} ativos`}
                    />
                    {p.scheduler.next && (
                      <Metric label="Próximo disparo" value={p.scheduler.next.replace('T', ' ')} />
                    )}
                  </>
                )}
              </Card>

              <div className="flex gap-2 mt-2">
                <Button onClick={() => setVerGrafo(!verGrafo)}>
                  {verGrafo ? 'Ver lista' : 'Ver o DAG'}
                </Button>
                <Button variant="ghost" onClick={recarregarLista}>
                  Recarregar tarefas
                </Button>
              </div>

              {verGrafo ? (
                <Dag onSelect={setSelecionada} selecionada={selecionada} />
              ) : (
                <Split
                  amplo={amplo}
                  lado={
                    selecionada && (
                      <Quadro estado={detalhe} onRetry={recarregarDetalhe}>
                        {(d) => (
                          <DetalheTarefa
                            d={d}
                            onFechar={() => setSelecionada(undefined)}
                            onIr={setSelecionada}
                          />
                        )}
                      </Quadro>
                    )
                  }
                  principal={
                    <Quadro
                      estado={lista}
                      onRetry={recarregarLista}
                      vazio={(t) => t.length === 0}
                      vazioTitulo={filtro ? `Nenhuma tarefa em "${filtro}"` : 'Nenhuma tarefa'}
                      vazioDicas={['Use `ragx task plan "..." --apply` para criar um plano.']}
                    >
                      {(tarefas) => (
                        <div className="space-y-1 mt-2">
                          {tarefas.map((t) => (
                            <Linha
                              key={t.id}
                              t={t}
                              ativa={t.id === selecionada}
                              onClick={() =>
                                setSelecionada(t.id === selecionada ? undefined : t.id)
                              }
                            />
                          ))}
                        </div>
                      )}
                    </Quadro>
                  }
                />
              )}
            </>
          )
        }
      </Quadro>
    </div>
  );
}

function Chip({
  children,
  ativo,
  onClick,
}: {
  children: React.ReactNode;
  ativo: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      onClick={onClick}
      className={`inline-flex items-center gap-1 px-1.5 py-[1px] rounded text-[0.85em]
                  border ${ativo ? 'border-focus bg-active-soft' : 'border-border hover:bg-hover'}`}
    >
      {children}
    </button>
  );
}

function Linha({ t, ativa, onClick }: { t: TaskInfo; ativa: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={ativa}
      className={`w-full text-left border rounded p-2 hover:bg-hover transition-colors ${
        ativa ? 'border-focus bg-active-soft' : 'border-border'
      }`}
    >
      <div className="flex items-center gap-1.5 flex-wrap">
        <Badge tone={TOM[t.status] ?? 'neutral'}>{t.status}</Badge>
        <span className="truncate font-semibold">{t.title}</span>
        {t.requiresApproval && (
          <Badge tone="warn" title="Só sai do lugar com aprovação humana">
            aprovação
          </Badge>
        )}
        {t.retryCount > 0 && <Badge tone="warn">retry {t.retryCount}</Badge>}
      </div>
      <p className="text-fg-muted text-[0.85em] font-mono truncate mt-0.5">
        {t.id}
        {t.track ? ` · ${t.track}` : ''}
        {t.priority ? ` · ${t.priority}` : ''}
      </p>
    </button>
  );
}

function DetalheTarefa({
  d,
  onFechar,
  onIr,
}: {
  d: TaskDetail;
  onFechar: () => void;
  onIr: (id: string) => void;
}) {
  const t = d.task;
  return (
    <Card
      title={t.title}
      action={
        <Button variant="ghost" onClick={onFechar}>
          Fechar
        </Button>
      }
    >
      <div className="flex flex-wrap gap-1 mb-2">
        <Badge tone={TOM[t.status] ?? 'neutral'}>{t.status}</Badge>
        {t.track && <Badge>{t.track}</Badge>}
        {t.type && <Badge>{t.type}</Badge>}
        {t.requiresApproval && <Badge tone="warn">exige aprovação</Badge>}
      </div>

      <p className="font-mono text-[0.85em] text-fg-muted break-all mb-2">{t.id}</p>
      {t.description && <p className="text-[0.95em] mb-2">{t.description}</p>}

      {t.assignee && <Metric label="Responsável" value={t.assignee} />}
      {t.leaseExpiresAt && (
        <Metric label="Lease até" value={t.leaseExpiresAt.replace('T', ' ').slice(0, 16)} />
      )}
      {t.updatedAt && (
        <Metric label="Atualizada" value={t.updatedAt.replace('T', ' ').slice(0, 16)} />
      )}

      <Secao titulo="Critérios de aceite" itens={t.acceptanceCriteria} />
      <Secao titulo="Testes exigidos" itens={t.testRequirements ?? []} />
      <Secao titulo="Segurança" itens={t.securityRequirements ?? []} />

      {t.filesScope.length > 0 && (
        <div className="mt-2">
          <p className="font-semibold text-[0.9em] mb-1">Escopo de arquivos</p>
          {t.filesScope.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => send({ type: 'openFile', path: f, line: 1 })}
              className="block text-link hover:underline text-[0.9em] text-left truncate w-full"
            >
              {f}
            </button>
          ))}
        </div>
      )}

      {d.dependencies.length > 0 && (
        <Relacionadas titulo="Depende de" refs={d.dependencies} onIr={onIr} />
      )}
      {d.dependents.length > 0 && (
        <Relacionadas titulo="Destrava" refs={d.dependents} onIr={onIr} />
      )}

      {d.lastResult && (
        <div className="mt-3 pt-2 border-t border-border">
          <p className="font-semibold text-[0.9em] mb-1">Último resultado</p>
          {d.lastResult.status && <Metric label="Status" value={d.lastResult.status} />}
          {d.lastResult.summary && (
            <p className="text-fg-muted text-[0.9em] mt-1">{d.lastResult.summary}</p>
          )}
          {d.lastResult.checks?.length ? (
            <ul className="mt-1 space-y-0.5">
              {d.lastResult.checks.map((c, i) => (
                <li key={i} className="flex items-center justify-between text-[0.9em]">
                  <span>{c.name}</span>
                  <Badge tone={c.passed ? 'ok' : 'err'}>{c.passed ? '✓' : '✗'}</Badge>
                </li>
              ))}
            </ul>
          ) : null}
          {d.lastResult.filesChanged?.length ? (
            <div className="mt-1">
              <p className="text-fg-muted text-[0.9em]">Arquivos alterados</p>
              {d.lastResult.filesChanged.map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => send({ type: 'openFile', path: f, line: 1 })}
                  className="block text-link hover:underline text-[0.9em] text-left truncate w-full"
                >
                  {f}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      )}

      <p className="text-fg-muted text-[0.85em] mt-3">
        Para executar: <code>ragx task run {t.id.slice(0, 12)}…</code>. O plugin
        não reivindica nem reporta tarefa.
      </p>
    </Card>
  );
}

function Secao({ titulo, itens }: { titulo: string; itens: string[] }) {
  if (!itens.length) return null;
  return (
    <div className="mt-2">
      <p className="font-semibold text-[0.9em] mb-1">{titulo}</p>
      <ul className="text-[0.9em] text-fg-muted space-y-0.5">
        {itens.map((i, n) => (
          <li key={n}>• {i}</li>
        ))}
      </ul>
    </div>
  );
}

function Relacionadas({
  titulo,
  refs,
  onIr,
}: {
  titulo: string;
  refs: Array<{ id: string; title?: string; status?: string }>;
  onIr: (id: string) => void;
}) {
  return (
    <div className="mt-2">
      <p className="font-semibold text-[0.9em] mb-1">{titulo}</p>
      {refs.map((r) => (
        <button
          key={r.id}
          type="button"
          onClick={() => onIr(r.id)}
          className="flex items-center gap-1.5 w-full text-left text-[0.9em] py-0.5
                     hover:bg-hover rounded px-1"
        >
          {r.status && <Badge tone={TOM[r.status] ?? 'neutral'}>{r.status}</Badge>}
          <span className="truncate text-link">{r.title || r.id}</span>
        </button>
      ))}
    </div>
  );
}

/**
 * O DAG em camadas, não em forças.
 *
 * Dependência é uma ordem, e ordem se lê de cima para baixo. Um layout por
 * forças embaralharia exatamente a informação que importa aqui: o que vem
 * antes de quê.
 */
function Dag({
  onSelect,
  selecionada,
}: {
  onSelect: (id: string) => void;
  selecionada?: string;
}) {
  const [estado, recarregar] = usePedido<TaskGraph>(
    () => request({ type: 'getTaskGraph' }, 'taskGraph').then((r) => r.graph),
    [],
  );

  return (
    <Quadro estado={estado} onRetry={recarregar} vazio={(g) => g.nodes.length === 0}>
      {(g) => {
        const camadas = ordenar(g);
        return (
          <div className="space-y-3 mt-2">
            {camadas.map((camada, i) => (
              <div key={i}>
                <p className="text-fg-muted text-[0.8em] mb-1">
                  {i === 0 ? 'Pode começar agora' : `Depois de ${i} nível(is)`}
                </p>
                <Grade min={220}>
                  {camada.map((n) => (
                    <button
                      key={n.id}
                      type="button"
                      onClick={() => onSelect(n.id)}
                      className={`text-left border rounded p-2 hover:bg-hover ${
                        n.id === selecionada ? 'border-focus bg-active-soft' : 'border-border'
                      }`}
                    >
                      <Badge tone={TOM[n.status] ?? 'neutral'}>{n.status}</Badge>
                      <p className="truncate mt-1">{n.title}</p>
                    </button>
                  ))}
                </Grade>
              </div>
            ))}
            <p className="text-fg-muted text-[0.85em]">
              {g.nodes.length} tarefa(s) · {g.edges.length} dependência(s)
            </p>
          </div>
        );
      }}
    </Quadro>
  );
}

/**
 * Camadas topológicas. Ciclo vira a última camada, visível em vez de escondido.
 *
 * O RAGX recusa criar ciclo, mas um banco escrito por outra versão ainda pode
 * ter um — e sumir com as tarefas envolvidas seria a pior resposta possível.
 */
function ordenar(g: TaskGraph): TaskGraph['nodes'][] {
  const restantes = new Map(g.nodes.map((n) => [n.id, n]));
  const dependencias = new Map<string, Set<string>>();
  for (const n of g.nodes) dependencias.set(n.id, new Set());
  for (const e of g.edges) dependencias.get(e.from)?.add(e.to);

  const camadas: TaskGraph['nodes'][] = [];
  const resolvidos = new Set<string>();

  while (restantes.size) {
    const camada = [...restantes.values()].filter((n) =>
      [...(dependencias.get(n.id) ?? [])].every((d) => resolvidos.has(d) || !restantes.has(d)),
    );
    if (!camada.length) {
      camadas.push([...restantes.values()]);
      break;
    }
    for (const n of camada) {
      restantes.delete(n.id);
      resolvidos.add(n.id);
    }
    camadas.push(camada);
  }
  return camadas;
}

/**
 * O Task Analyzer, na tela.
 *
 * Classifica um pedido e mostra POR QUE classificou assim — as sete dimensões
 * e os sinais que bateram. Não escreve nada: `plan --apply` continua sendo uma
 * decisão explícita, tomada fora daqui.
 */
function Analisador({ inicial }: { inicial?: string }) {
  const [texto, setTexto] = useState(inicial ?? '');
  const [pedido, setPedido] = useState(inicial ?? '');
  const [aberto, setAberto] = useState(Boolean(inicial));

  useEffect(() => {
    if (inicial) {
      setTexto(inicial);
      setPedido(inicial);
      setAberto(true);
    }
  }, [inicial]);

  const [estado, recarregar] = usePedido<RequestAnalysis>(
    () => request({ type: 'analyzeRequest', request: pedido }, 'analysis').then((r) => r.analysis),
    [pedido],
    pedido.trim().length > 3,
  );

  if (!aberto) {
    return (
      <Button onClick={() => setAberto(true)}>Analisar um pedido antes de começar</Button>
    );
  }

  return (
    <Card
      title="Analisar pedido"
      action={
        <Button variant="ghost" onClick={() => setAberto(false)}>
          Fechar
        </Button>
      }
    >
      <div className="flex gap-2">
        <Input
          label="Pedido a classificar"
          value={texto}
          onChange={setTexto}
          onEnter={() => setPedido(texto.trim())}
          placeholder="migrar a autenticação para SSO em todos os serviços"
        />
        <Button variant="primary" onClick={() => setPedido(texto.trim())}>
          Analisar
        </Button>
      </div>

      {pedido.trim().length > 3 && (
        <div className="mt-2">
          <Quadro estado={estado} onRetry={recarregar}>
            {(a) => (
              <>
                <div className="flex items-center gap-2 flex-wrap mb-2">
                  <Badge tone={a.requiresDecomposition ? 'warn' : 'ok'}>{a.classification}</Badge>
                  <Badge>{a.strategy}</Badge>
                  <Badge>complexidade {a.complexity}</Badge>
                  <span className="text-fg-muted text-[0.85em] ml-auto">
                    confiança {(a.confidence * 100).toFixed(0)}%
                  </span>
                </div>

                <Metric label="Pontuação" value={`${a.total}/100`} />
                {a.rawTotal !== a.total && (
                  // O total efetivo pode ser menor que o bruto por regra de
                  // redução. Mostrar só um dos dois esconderia a decisão.
                  <Metric label="Bruto (sem redução)" value={`${a.rawTotal}/100`} />
                )}
                <div className="mt-2 space-y-1">
                  {Object.entries(a.scores)
                    .filter(([, v]) => v > 0)
                    .sort((x, y) => y[1] - x[1])
                    .map(([dim, v]) => (
                      <div key={dim}>
                        <p className="text-fg-muted text-[0.85em]">{dim}</p>
                        <Bar label={dim} value={v} />
                      </div>
                    ))}
                </div>

                {a.reasoning && <p className="text-[0.95em] mt-2">{a.reasoning}</p>}
                {a.overrideReason && (
                  <p className="text-warn text-[0.9em] mt-1">
                    Ajustado por {a.overriddenBy}: {a.overrideReason}
                  </p>
                )}

                <div className="flex flex-wrap gap-1 mt-2">
                  {a.matchedSignals.slice(0, 20).map((s) => (
                    <Badge key={s} tone="info">
                      {s}
                    </Badge>
                  ))}
                </div>

                <Secao titulo="Riscos" itens={a.risks} />
                <Secao titulo="Dependências" itens={a.dependencies} />

                <p className="text-fg-muted text-[0.85em] mt-3">
                  {a.requiresDecomposition
                    ? 'Este pedido pede documentação e decomposição antes do código. ' +
                      'Para criar o plano: `ragx task plan "..." --apply`.'
                    : 'Pequeno o bastante para executar direto. Nada foi criado.'}
                </p>
              </>
            )}
          </Quadro>
        </div>
      )}
    </Card>
  );
}
