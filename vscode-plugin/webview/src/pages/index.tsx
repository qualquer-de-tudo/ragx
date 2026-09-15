/**
 * As telas do MVP (§54).
 *
 * Toda página segue o mesmo contrato de estados: `loading`, `ready`, `empty`,
 * `error`. Nenhuma delas tem caminho que leve a uma tela em branco (§44) — e o
 * `usePedido` abaixo existe justamente para que isso não dependa de disciplina.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import type { UiError, UiSettings } from '../../../src/protocol';
import type {
  AgentInfo,
  ContextPack,
  DictionarySection,
  EntityDetail,
  FileKnowledge,
  GraphNode,
  GraphSlice,
  HealthCheck,
  KnowledgeStats,
  MonitorSnapshot,
  SearchHit,
  SearchMode,
  SearchResponse,
  SecurityStatus,
} from '../../../src/rag/types';
import { request, send, toUiError } from '../bridge';
import {
  Badge,
  Bar,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  Loading,
  Metric,
  Tabs,
  Tree,
  VirtualList,
  fmt,
  useDebounced,
  type TreeNode,
} from '../components';
import { GraphView } from '../components/GraphView';

// ── carregamento com estado completo ────────────────────────────────────
type Estado<T> =
  | { fase: 'loading' }
  | { fase: 'ready'; dado: T }
  | { fase: 'error'; erro: UiError };

function usePedido<T>(
  carregar: () => Promise<T>,
  deps: unknown[],
  ativo = true,
): [Estado<T>, () => void] {
  const [estado, setEstado] = useState<Estado<T>>({ fase: 'loading' });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!ativo) return;
    let cancelado = false;
    setEstado({ fase: 'loading' });
    carregar()
      .then((dado) => !cancelado && setEstado({ fase: 'ready', dado }))
      .catch((e) => !cancelado && setEstado({ fase: 'error', erro: toUiError(e) }));
    return () => {
      cancelado = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, ativo]);

  return [estado, () => setTick((t) => t + 1)];
}

function Quadro<T>({
  estado,
  onRetry,
  vazio,
  children,
}: {
  estado: Estado<T>;
  onRetry: () => void;
  vazio?: (d: T) => boolean;
  children: (d: T) => React.ReactNode;
}) {
  if (estado.fase === 'loading') return <Loading />;
  if (estado.fase === 'error') {
    return (
      <ErrorState
        error={estado.erro}
        onRetry={onRetry}
        onLogs={() => send({ type: 'openLogs' })}
        onSettings={() => send({ type: 'openSettings' })}
      />
    );
  }
  if (vazio?.(estado.dado)) {
    return <EmptyState title="Nada aqui ainda" hints={['Rode `ragx index .` e sincronize.']} />;
  }
  return <>{children(estado.dado)}</>;
}

// ── Overview ────────────────────────────────────────────────────────────
export function Overview({ onGo }: { onGo: (p: string) => void }) {
  const [estado, recarregar] = usePedido<KnowledgeStats>(
    () => request({ type: 'getStats' }, 'stats').then((r) => r.stats),
    [],
  );
  const [saude] = usePedido<HealthCheck[]>(
    () => request({ type: 'getHealth' }, 'health').then((r) => r.checks),
    [],
  );

  return (
    <div className="space-y-3">
      <Quadro estado={estado} onRetry={recarregar}>
        {(s) => (
          <>
            <Card title="Knowledge Overview">
              <Metric label="Documents" value={fmt(s.documents)} />
              <Metric label="Chunks" value={fmt(s.chunks)} />
              <Metric label="Entities" value={fmt(s.entities)} />
              <Metric label="Relations" value={fmt(s.relations)} />
              <div className="mt-3 space-y-2">
                <div>
                  <p className="text-fg-muted text-[0.9em] mb-1">Embeddings</p>
                  <Bar
                    label="Cobertura de embeddings"
                    value={s.chunks ? (s.embeddings / s.chunks) * 100 : 0}
                  />
                </div>
                {s.lastRun?.finishedAt && (
                  <Metric label="Last sync" value={s.lastRun.finishedAt.replace('T', ' ').replace('Z', '')} />
                )}
              </div>
            </Card>

            {Object.keys(s.byLang).length > 0 && (
              <Card title="Por linguagem">
                {Object.entries(s.byLang)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 8)
                  .map(([lang, n]) => (
                    <Metric key={lang} label={lang} value={fmt(n)} />
                  ))}
              </Card>
            )}
          </>
        )}
      </Quadro>

      {saude.fase === 'ready' && (
        <Card
          title="Health"
          action={
            <Button variant="ghost" onClick={() => send({ type: 'sync' })}>
              Sync
            </Button>
          }
        >
          {saude.dado.map((c) => (
            <div key={c.name} className="flex items-center justify-between py-0.5">
              <span>{c.name}</span>
              <Badge tone={c.status === 'ok' ? 'ok' : c.status === 'warn' ? 'warn' : 'err'}>
                {c.status === 'ok' ? '✓ ok' : c.status === 'warn' ? '⚠ atenção' : '✗ erro'}
                {c.detail ? ` — ${c.detail}` : ''}
              </Badge>
            </div>
          ))}
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => onGo('search')}>
          Buscar conhecimento
        </Button>
        <Button onClick={() => onGo('graph')}>Explorar grafo</Button>
        <Button onClick={() => onGo('context')}>Montar contexto</Button>
      </div>
    </div>
  );
}

// ── Search ──────────────────────────────────────────────────────────────
export function Search({
  settings,
  consultaInicial,
  onEntity,
}: {
  settings: UiSettings;
  consultaInicial?: string;
  onEntity: (nome: string) => void;
}) {
  const [texto, setTexto] = useState(consultaInicial ?? '');
  const [modo, setModo] = useState<SearchMode>(settings.searchMode);
  const [abrirFiltros, setAbrirFiltros] = useState(false);
  const [lang, setLang] = useState('');
  const [kind, setKind] = useState('');
  const consulta = useDebounced(texto, 350);

  useEffect(() => {
    if (consultaInicial) setTexto(consultaInicial);
  }, [consultaInicial]);

  const [estado, recarregar] = usePedido<SearchResponse>(
    () =>
      request(
        {
          type: 'search',
          query: consulta,
          mode: modo,
          limit: 30,
          filters: {
            lang: lang || undefined,
            kind: kind || undefined,
          },
        },
        'search',
      ).then((r) => r.response),
    [consulta, modo, lang, kind],
    consulta.trim().length >= 2,
  );

  return (
    <div className="space-y-2">
      <Input
        label="Buscar no conhecimento"
        value={texto}
        onChange={setTexto}
        autoFocus
        placeholder="como funciona a autenticação?"
      />

      <div className="flex items-center gap-2 flex-wrap">
        <Tabs
          label="Modo de busca"
          active={modo}
          onChange={setModo}
          items={[
            { id: 'hybrid', label: 'Híbrida' },
            { id: 'semantic', label: 'Semântica' },
            { id: 'keyword', label: 'Palavra-chave' },
          ]}
        />
        <Button variant="ghost" onClick={() => setAbrirFiltros(!abrirFiltros)}>
          Filtros {abrirFiltros ? '▾' : '▸'}
        </Button>
      </div>

      {abrirFiltros && (
        <div className="grid grid-cols-2 gap-2 p-2 border border-border rounded">
          <label className="text-[0.9em] text-fg-muted">
            Linguagem
            <Input label="Filtrar por linguagem" value={lang} onChange={setLang} placeholder="python" />
          </label>
          <label className="text-[0.9em] text-fg-muted">
            Tipo
            <Input label="Filtrar por tipo" value={kind} onChange={setKind} placeholder="function" />
          </label>
          <div className="col-span-2">
            <Button
              onClick={() => {
                setLang('');
                setKind('');
              }}
            >
              Limpar filtros
            </Button>
          </div>
        </div>
      )}

      {consulta.trim().length < 2 ? (
        <EmptyState
          title="Busque no conhecimento do projeto"
          hints={[
            'Faça uma pergunta em linguagem natural',
            'Ou procure por um símbolo específico',
            'Híbrida combina sentido e palavra literal',
          ]}
        />
      ) : (
        <Quadro
          estado={estado}
          onRetry={recarregar}
          vazio={(r) => r.results.length === 0}
        >
          {(r) => (
            <div className="space-y-1">
              <p className="text-fg-muted text-[0.85em]">
                {r.results.length} resultado(s) · {r.mode}
                {r.degraded ? ` · degradado: ${r.degraded}` : ''}
              </p>
              {r.results.map((h) => (
                <Resultado key={h.chunkId} hit={h} onEntity={onEntity} />
              ))}
            </div>
          )}
        </Quadro>
      )}

      {estado.fase === 'ready' && estado.dado.results.length === 0 && (
        <EmptyState
          title="Nenhum conhecimento encontrado"
          hints={[
            'Tente uma busca mais ampla',
            'Ou outra formulação da pergunta',
            'Remova os filtros',
          ]}
          action={
            <Button
              onClick={() => {
                setLang('');
                setKind('');
              }}
            >
              Limpar filtros
            </Button>
          }
        />
      )}
    </div>
  );
}

function Resultado({ hit, onEntity }: { hit: SearchHit; onEntity: (n: string) => void }) {
  const [aberto, setAberto] = useState(false);
  const pct = Math.round(Math.min(1, hit.score * 10) * 100);
  const literal = hit.matchedBy.includes('keyword');

  return (
    <article className="border border-border rounded hover:bg-hover/40">
      <div className="flex items-start gap-2 p-2">
        <span
          className="font-mono text-[0.85em] text-fg-muted w-10 shrink-0 tabular-nums"
          title={`score ${hit.score.toFixed(4)}`}
        >
          {pct}%
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap">
            <button
              type="button"
              onClick={() =>
                send({ type: 'openFile', path: hit.documentPath, line: hit.lines[0] })
              }
              className="text-link hover:text-link-active hover:underline truncate text-left"
              title={`${hit.documentPath}:${hit.lines[0]}`}
            >
              {hit.documentPath}
            </button>
            <span className="text-fg-muted text-[0.85em]">:{hit.lines[0]}</span>
            {/* `keyword` significa que o termo literal está lá. Vale muito mais
                que `semantic`, e a UI precisa deixar isso à vista. */}
            <Badge tone={literal ? 'ok' : 'neutral'} title={hit.matchedBy.join(', ')}>
              {literal ? 'literal' : 'semântico'}
            </Badge>
            {hit.documentPath.startsWith('@base/') && (
              <Badge tone="info" title="Conhecimento base compartilhado, fora deste repositório">
                @base
              </Badge>
            )}
          </div>
          {hit.headingPath && (
            <p className="text-fg-muted text-[0.85em] truncate">{hit.headingPath}</p>
          )}
          <pre className="mt-1 text-[0.9em] font-mono whitespace-pre-wrap break-words text-fg-muted">
            {aberto ? hit.content : hit.content.slice(0, 220)}
            {!aberto && hit.content.length > 220 ? '…' : ''}
          </pre>
          <div className="flex gap-1 mt-1">
            {hit.content.length > 220 && (
              <Button variant="ghost" onClick={() => setAberto(!aberto)}>
                {aberto ? 'Menos' : 'Mais'}
              </Button>
            )}
            <Button
              variant="ghost"
              onClick={() => send({ type: 'openFile', path: hit.documentPath, line: hit.lines[0] })}
            >
              Abrir
            </Button>
            {hit.symbol && (
              <Button variant="ghost" onClick={() => onEntity(hit.symbol!)}>
                Ver no grafo
              </Button>
            )}
            <Button variant="ghost" onClick={() => send({ type: 'copy', text: hit.content })}>
              Copiar
            </Button>
          </div>
        </div>
      </div>
    </article>
  );
}

// ── Graph ───────────────────────────────────────────────────────────────
export function Graph({
  settings,
  entidadeInicial,
}: {
  settings: UiSettings;
  entidadeInicial?: string;
}) {
  const [busca, setBusca] = useState(entidadeInicial ?? '');
  const [entidade, setEntidade] = useState(entidadeInicial ?? '');
  const [profundidade, setProfundidade] = useState(1);
  const [selecionado, setSelecionado] = useState<GraphNode | undefined>();
  const [acumulado, setAcumulado] = useState<GraphSlice>({ nodes: [], edges: [] });

  useEffect(() => {
    if (entidadeInicial) {
      setBusca(entidadeInicial);
      setEntidade(entidadeInicial);
    }
  }, [entidadeInicial]);

  const [estado, recarregar] = usePedido<GraphSlice>(
    () =>
      request({ type: 'getGraph', entity: entidade, depth: profundidade }, 'graph').then(
        (r) => r.graph,
      ),
    [entidade, profundidade],
    entidade.trim().length > 0,
  );

  useEffect(() => {
    if (estado.fase === 'ready') setAcumulado(estado.dado);
  }, [estado]);

  const [detalhe] = usePedido<EntityDetail>(
    () =>
      request({ type: 'getEntity', name: selecionado!.name }, 'entity').then((r) => r.entity),
    [selecionado?.name],
    Boolean(selecionado),
  );

  /** Expansão progressiva: carrega os vizinhos DAQUELE nó e funde (§12). */
  const expandir = useCallback(
    async (n: GraphNode) => {
      try {
        const r = await request(
          { type: 'getGraph', entity: n.name, depth: 1 },
          'graph',
        );
        setAcumulado((atual) => fundir(atual, r.graph, settings.maxVisibleNodes, n.id));
      } catch {
        /* falha de expansão não desmonta o que já está na tela */
      }
    },
    [settings.maxVisibleNodes],
  );

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          label="Entidade para explorar"
          value={busca}
          onChange={setBusca}
          onEnter={() => setEntidade(busca.trim())}
          placeholder="AuthService"
        />
        <Button variant="primary" onClick={() => setEntidade(busca.trim())}>
          Explorar
        </Button>
      </div>

      <label className="flex items-center gap-2 text-[0.9em] text-fg-muted">
        Profundidade
        <select
          value={profundidade}
          onChange={(e) => setProfundidade(Number(e.target.value))}
          className="bg-bg-input text-fg-input border border-border-input rounded px-1 py-0.5"
        >
          {Array.from({ length: settings.graphMaxDepth }, (_, i) => i + 1).map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <span className="ml-auto">máx. {settings.maxVisibleNodes} nós visíveis</span>
      </label>

      {!entidade ? (
        <EmptyState
          title="Sem dados de grafo"
          hints={['Digite o nome de uma entidade para explorar as relações dela.']}
        />
      ) : (
        <Quadro estado={estado} onRetry={recarregar}>
          {() => (
            <GraphView
              graph={acumulado}
              center={acumulado.nodes.find((n) => n.name === entidade)?.id}
              selectedId={selecionado?.id}
              onSelect={setSelecionado}
              onExpand={(n) => void expandir(n)}
            />
          )}
        </Quadro>
      )}

      {selecionado && detalhe.fase === 'ready' && (
        <Card title={detalhe.dado.entity.name}>
          <Metric label="Tipo" value={detalhe.dado.entity.type} />
          {detalhe.dado.entity.summary && (
            <p className="text-fg-muted text-[0.9em] mt-1">{detalhe.dado.entity.summary}</p>
          )}
          {detalhe.dado.relations.length > 0 && (
            <div className="mt-2">
              <p className="font-semibold text-[0.9em] mb-1">Relações</p>
              <ul className="text-[0.9em] space-y-0.5">
                {detalhe.dado.relations.slice(0, 20).map((r, i) => (
                  <li key={i} className="font-mono text-fg-muted">
                    {r.direction === 'out' ? '→' : '←'} {r.type} {r.target}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {detalhe.dado.sources.length > 0 && (
            <div className="mt-2">
              <p className="font-semibold text-[0.9em] mb-1">Fontes</p>
              {detalhe.dado.sources.map((s, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => send({ type: 'openFile', path: s.path, line: s.line })}
                  className="block text-link hover:underline text-[0.9em] text-left"
                >
                  {s.path}
                  {s.line ? `:${s.line}` : ''}
                </button>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function fundir(
  atual: GraphSlice,
  novo: GraphSlice,
  maxNos: number,
  expandidoId: string,
): GraphSlice {
  const nodes = new Map(atual.nodes.map((n) => [n.id, n]));
  const marcado = nodes.get(expandidoId);
  if (marcado) nodes.set(expandidoId, { ...marcado, expanded: true });

  for (const n of novo.nodes) {
    if (nodes.size >= maxNos && !nodes.has(n.id)) continue;
    if (!nodes.has(n.id)) nodes.set(n.id, n);
  }
  const chave = (e: { source: string; target: string; type: string }) =>
    `${e.source}|${e.target}|${e.type}`;
  const edges = new Map(atual.edges.map((e) => [chave(e), e]));
  for (const e of novo.edges) {
    if (nodes.has(e.source) && nodes.has(e.target)) edges.set(chave(e), e);
  }
  return {
    nodes: [...nodes.values()],
    edges: [...edges.values()],
    truncated: atual.truncated || novo.truncated || nodes.size >= maxNos,
  };
}

// ── Dictionary ──────────────────────────────────────────────────────────
export function Dictionary({ onEntity }: { onEntity: (n: string) => void }) {
  const [estado, recarregar] = usePedido<DictionarySection[]>(
    () => request({ type: 'getDictionary' }, 'dictionary').then((r) => r.sections),
    [],
  );
  const [filtro, setFiltro] = useState('');

  return (
    <div className="space-y-2">
      <Input label="Filtrar dicionário" value={filtro} onChange={setFiltro} placeholder="filtrar…" />
      <Quadro estado={estado} onRetry={recarregar} vazio={(s) => s.length === 0}>
        {(secoes) => {
          const arvore: TreeNode[] = secoes
            .map((s) => ({
              id: s.id,
              label: s.label,
              hint: String(s.items.length),
              children: s.items
                .filter(
                  (i) =>
                    !filtro ||
                    i.name.toLowerCase().includes(filtro.toLowerCase()) ||
                    i.description?.toLowerCase().includes(filtro.toLowerCase()),
                )
                .slice(0, 200)
                .map((i) => ({
                  id: `${s.id}/${i.name}`,
                  label: i.name,
                  hint: i.related?.length ? String(i.related.length) : undefined,
                })),
            }))
            .filter((s) => s.children.length > 0);

          if (!arvore.length) {
            return (
              <EmptyState
                title="Nada corresponde ao filtro"
                action={<Button onClick={() => setFiltro('')}>Limpar</Button>}
              />
            );
          }
          return (
            <Tree
              nodes={arvore}
              onSelect={(n) => onEntity(n.label)}
            />
          );
        }}
      </Quadro>
    </div>
  );
}

// ── Documents ───────────────────────────────────────────────────────────
export function Documents({ caminhoInicial }: { caminhoInicial?: string }) {
  const [busca, setBusca] = useState('');
  const consulta = useDebounced(busca, 350);
  const [selecionado, setSelecionado] = useState<string | undefined>(caminhoInicial);

  useEffect(() => {
    if (caminhoInicial) setSelecionado(caminhoInicial);
  }, [caminhoInicial]);

  const [lista, recarregarLista] = usePedido(
    () =>
      request({ type: 'getDocuments', query: consulta || undefined }, 'documents').then(
        (r) => r.documents,
      ),
    [consulta],
  );

  const [conhecimento, recarregarConhecimento] = usePedido<FileKnowledge>(
    () =>
      request({ type: 'getFileKnowledge', path: selecionado! }, 'fileKnowledge').then(
        (r) => r.knowledge,
      ),
    [selecionado],
    Boolean(selecionado),
  );

  return (
    <div className="space-y-2">
      {selecionado && (
        <Card
          title={selecionado}
          action={
            <Button variant="ghost" onClick={() => setSelecionado(undefined)}>
              Fechar
            </Button>
          }
        >
          <Quadro estado={conhecimento} onRetry={recarregarConhecimento}>
            {(k) =>
              k.indexed ? (
                <>
                  <div className="flex items-center gap-2 mb-2">
                    <Badge tone="ok">✓ indexado</Badge>
                    <Badge>{k.chunks.length} chunks</Badge>
                    {k.document?.redacted && (
                      <Badge tone="warn" title="Trechos sensíveis foram redigidos pelo gate">
                        redigido
                      </Badge>
                    )}
                  </div>
                  {k.entities.length > 0 && (
                    <div className="mb-2">
                      <p className="text-fg-muted text-[0.9em]">Símbolos</p>
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {k.entities.map((e) => (
                          <Badge key={e}>{e}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  <Button
                    onClick={() => send({ type: 'openFile', path: k.path, line: 1 })}
                    variant="primary"
                  >
                    Abrir arquivo
                  </Button>
                </>
              ) : (
                // Não indexado e bloqueado são indistinguíveis de fora — e é
                // assim que deve ser. A UI diz os dois, sem inventar um.
                <EmptyState
                  title="Não está no índice"
                  hints={[
                    k.reason ?? 'Este arquivo não foi indexado.',
                    'Pode ser que o Security Gate o tenha bloqueado por conter segredo.',
                  ]}
                  action={<Button onClick={() => send({ type: 'sync' })}>Sincronizar</Button>}
                />
              )
            }
          </Quadro>
        </Card>
      )}

      <Input label="Filtrar documentos" value={busca} onChange={setBusca} placeholder="filtrar documentos…" />
      <Quadro estado={lista} onRetry={recarregarLista} vazio={(d) => d.length === 0}>
        {(docs) => (
          <VirtualList
            items={docs}
            itemHeight={30}
            height={Math.min(420, docs.length * 30 + 4)}
            render={(d) => (
              <button
                type="button"
                onClick={() => setSelecionado(d.path)}
                className="w-full flex items-center gap-2 px-2 py-1 text-left rounded hover:bg-hover truncate"
              >
                <span className="truncate">{d.path}</span>
                <span className="ml-auto text-fg-muted font-mono text-[0.85em] shrink-0">
                  {d.chunks}
                </span>
              </button>
            )}
          />
        )}
      </Quadro>
    </div>
  );
}

// ── Context Builder ─────────────────────────────────────────────────────
export function Context({ settings }: { settings: UiSettings }) {
  const [texto, setTexto] = useState('');
  const [consulta, setConsulta] = useState('');
  const [orcamento, setOrcamento] = useState(settings.contextTokenBudget);
  const [excluidos, setExcluidos] = useState<Set<string>>(new Set());

  const [estado, recarregar] = usePedido<ContextPack>(
    () =>
      request({ type: 'buildContext', query: consulta, tokens: orcamento }, 'context').then(
        (r) => r.pack,
      ),
    [consulta, orcamento],
    consulta.trim().length > 2,
  );

  const pack = estado.fase === 'ready' ? estado.dado : undefined;
  const selecionados = useMemo(
    () => pack?.fragments.filter((f) => !excluidos.has(f.chunkId)) ?? [],
    [pack, excluidos],
  );
  const tokens = selecionados.reduce((s, f) => s + f.tokens, 0);

  const markdown = useMemo(() => {
    if (!selecionados.length) return '';
    const partes = [`# Contexto — ${consulta}`, ''];
    for (const f of selecionados) {
      partes.push(`## \`${f.documentPath}\`:${f.lines[0]}-${f.lines[1]}`, '', f.content, '');
    }
    return partes.join('\n');
  }, [selecionados, consulta]);

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          label="Tarefa para montar contexto"
          value={texto}
          onChange={setTexto}
          onEnter={() => setConsulta(texto.trim())}
          placeholder="implementar autenticação SSO"
        />
        <Button variant="primary" onClick={() => setConsulta(texto.trim())}>
          Montar
        </Button>
      </div>

      <label className="flex items-center gap-2 text-[0.9em] text-fg-muted">
        Orçamento
        <input
          type="range"
          min={500}
          max={16000}
          step={500}
          value={orcamento}
          onChange={(e) => setOrcamento(Number(e.target.value))}
          className="flex-1"
          aria-label="Orçamento de tokens"
        />
        <span className="font-mono tabular-nums w-14 text-right">{fmt(orcamento)}</span>
      </label>

      {!consulta ? (
        <EmptyState
          title="Monte o contexto de uma tarefa"
          hints={[
            'Descreva o que você vai fazer',
            'O RAGX escolhe os trechos e respeita o orçamento',
            'O ranking é do Context Engine, não desta tela',
          ]}
        />
      ) : (
        <Quadro estado={estado} onRetry={recarregar} vazio={(p) => p.fragments.length === 0}>
          {(p) => (
            <>
              <Card title="Contexto">
                <Metric label="Fontes" value={selecionados.length} />
                <Metric
                  label="Tokens"
                  value={`${fmt(tokens)} / ${fmt(p.budget)}`}
                />
                <div className="mt-2">
                  <Bar label="Uso do orçamento" value={(tokens / p.budget) * 100} />
                </div>
                <div className="flex flex-wrap gap-2 mt-3">
                  <Button
                    variant="primary"
                    disabled={!markdown}
                    onClick={() => send({ type: 'copy', text: markdown })}
                  >
                    Copiar
                  </Button>
                  <Button
                    disabled={!markdown}
                    onClick={() => send({ type: 'saveContext', markdown })}
                  >
                    Abrir como documento
                  </Button>
                  <Button onClick={() => setExcluidos(new Set())}>Restaurar todos</Button>
                </div>
              </Card>

              <div className="space-y-1 mt-2">
                {p.fragments.map((f) => {
                  const fora = excluidos.has(f.chunkId);
                  return (
                    <div
                      key={f.chunkId}
                      className={`border border-border rounded p-2 ${fora ? 'opacity-50' : ''}`}
                    >
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={!fora}
                          aria-label={`Incluir ${f.documentPath}`}
                          onChange={() =>
                            setExcluidos((s) => {
                              const n = new Set(s);
                              fora ? n.delete(f.chunkId) : n.add(f.chunkId);
                              return n;
                            })
                          }
                        />
                        <button
                          type="button"
                          onClick={() =>
                            send({ type: 'openFile', path: f.documentPath, line: f.lines[0] })
                          }
                          className="text-link hover:underline truncate text-left"
                        >
                          {f.documentPath}:{f.lines[0]}
                        </button>
                        <span className="ml-auto font-mono text-[0.85em] text-fg-muted shrink-0">
                          {f.tokens}t
                        </span>
                      </div>
                      <pre className="mt-1 text-[0.85em] font-mono whitespace-pre-wrap break-words text-fg-muted">
                        {f.content.slice(0, 200)}
                        {f.content.length > 200 ? '…' : ''}
                      </pre>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </Quadro>
      )}
    </div>
  );
}

// ── Monitor ─────────────────────────────────────────────────────────────
export function Monitor() {
  const [estado, recarregar] = usePedido<MonitorSnapshot>(
    () => request({ type: 'getMonitor' }, 'monitor').then((r) => r.monitor),
    [],
  );

  return (
    <Quadro estado={estado} onRetry={recarregar}>
      {(m) => (
        <div className="space-y-3">
          <Card title="RAGX Monitor" action={<Button variant="ghost" onClick={recarregar}>Atualizar</Button>}>
            <Metric label="Documents" value={fmt(m.stats.documents)} />
            <Metric label="Chunks" value={fmt(m.stats.chunks)} />
            <Metric label="Embeddings" value={fmt(m.stats.embeddings)} />
            <Metric label="Entities" value={fmt(m.stats.entities)} />
            <Metric label="Relations" value={fmt(m.stats.relations)} />
            {m.stats.lastRun?.finishedAt && (
              <Metric label="Last sync" value={m.stats.lastRun.finishedAt.replace('T', ' ').replace('Z', '')} />
            )}
          </Card>

          {m.tasks && Object.keys(m.tasks).length > 0 && (
            <Card title="Tarefas">
              {Object.entries(m.tasks).map(([estado, n]) => (
                <Metric key={estado} label={estado} value={fmt(n)} />
              ))}
            </Card>
          )}

          <Card title="Atividade recente">
            {m.activity.length === 0 ? (
              <p className="text-fg-muted text-[0.9em]">Nada registrado nesta sessão.</p>
            ) : (
              <ul className="text-[0.9em] space-y-0.5">
                {m.activity.map((a, i) => (
                  <li key={i} className="font-mono text-fg-muted">
                    {a.at.slice(11, 16)} {a.message}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </Quadro>
  );
}

// ── Security ────────────────────────────────────────────────────────────
export function Security() {
  const [estado, recarregar] = usePedido<SecurityStatus>(
    () => request({ type: 'getSecurity' }, 'security').then((r) => r.security),
    [],
  );

  return (
    <Quadro estado={estado} onRetry={recarregar}>
      {(s) => (
        <div className="space-y-3">
          <Card title="Security Status">
            {[
              ['Security Gate ativo', s.gateActive],
              ['.gitignore respeitado', s.ignoreFiles.includes('.gitignore')],
              ['.dockerignore respeitado', s.ignoreFiles.includes('.dockerignore')],
              ['.ragignore respeitado', s.ignoreFiles.includes('.ragignore')],
              ['Scanner de segredos ativo', s.gateActive],
            ].map(([rotulo, ok]) => (
              <div key={String(rotulo)} className="flex items-center justify-between py-0.5">
                <span>{rotulo}</span>
                <Badge tone={ok ? 'ok' : 'warn'}>{ok ? '✓ sim' : '⚠ não'}</Badge>
              </div>
            ))}
            <div className="mt-2 pt-2 border-t border-border">
              <Metric label="Política" value={s.policy} />
              <Metric label="Arquivos bloqueados" value={fmt(s.blockedFiles)} />
              <Metric label="Arquivos redigidos" value={fmt(s.redactedFiles)} />
            </div>
          </Card>

          <Card title="Segredos no índice">
            <Metric label="Indexados" value={fmt(s.indexedSecrets)} />
            <Metric label="Em embeddings" value={fmt(s.embeddedSecrets)} />
            <Metric label="Armazenados" value={0} />
            <p className="text-fg-muted text-[0.85em] mt-2">
              O gate roda antes do parser: o que ele bloqueia nunca entra no
              índice. Não é filtro de saída — é ausência.
            </p>
          </Card>

          {s.reasons.length > 0 && (
            <Card title="Motivos de bloqueio">
              {s.reasons.map((r) => (
                <Metric key={r.rule} label={r.rule} value={fmt(r.count)} />
              ))}
              {/* Agregado por REGRA. A lista de caminhos bloqueados é um mapa
                  de onde estão os segredos — nunca vai para a tela (§19). */}
              <p className="text-fg-muted text-[0.85em] mt-2">
                Agregado por regra. Os caminhos bloqueados não são exibidos: a
                lista de onde estão os segredos é, ela mesma, sensível.
              </p>
            </Card>
          )}
        </div>
      )}
    </Quadro>
  );
}

// ── Agents ──────────────────────────────────────────────────────────────
export function Agents() {
  const [estado, recarregar] = usePedido<AgentInfo[]>(
    () => request({ type: 'getAgents' }, 'agents').then((r) => r.agents),
    [],
  );

  return (
    <Quadro estado={estado} onRetry={recarregar} vazio={(a) => a.length === 0}>
      {(agentes) => (
        <div className="space-y-2">
          {agentes.map((a) => (
            <Card key={a.name} title={a.name}>
              <div className="mb-2">
                <Badge tone={a.state === 'ready' ? 'ok' : 'warn'}>
                  {a.state === 'ready' ? '● Ready' : `● ${a.state}`}
                </Badge>
              </div>
              {a.chunks !== undefined && <Metric label="Knowledge" value={`${fmt(a.chunks)} chunks`} />}
              {a.skills !== undefined && <Metric label="Skills" value={a.skills} />}
              {a.rules !== undefined && <Metric label="Rules" value={a.rules} />}
              {a.coverage !== undefined && (
                <div className="mt-2">
                  <p className="text-fg-muted text-[0.9em] mb-1">Coverage</p>
                  <Bar label={`Cobertura de ${a.name}`} value={a.coverage * 100} />
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </Quadro>
  );
}
