/**
 * As telas do explorador.
 *
 * Toda página segue o mesmo contrato de estados (`loading`, `ready`, `empty`,
 * `error`), garantido pelo `Quadro` em `estado.tsx` — nenhuma delas tem
 * caminho que leve a uma tela em branco (§44).
 *
 * Todas recebem `amplo`. Ele NÃO é um detalhe estético: na barra lateral
 * (~300px) a resposta certa é uma coluna e detalhe empilhado; na aba do editor
 * a mesma tela ganha uma segunda coluna e passa a servir para comparar, que é
 * o motivo de existir a versão em tela cheia.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';

import type { UiSettings } from '../../../src/protocol';
import type {
  AgentInfo,
  ChunkInfo,
  ContextPack,
  DictionarySection,
  DocumentInfo,
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
  SourcesOverview,
} from '../../../src/rag/types';
import { request, send } from '../bridge';
import {
  Badge,
  Bar,
  Button,
  Card,
  Codigo,
  EmptyState,
  Grade,
  Input,
  Metric,
  Split,
  Tabs,
  Tree,
  VirtualList,
  fmt,
  useDebounced,
  type TreeNode,
} from '../components';
import { GraphView } from '../components/GraphView';
import { Quadro, usePedido } from './estado';

export { Quadro, usePedido } from './estado';
export { Sources } from './sources';
export { Tasks } from './tasks';

/**
 * A origem de um caminho, deduzida do prefixo.
 *
 * `@base/<nome>/…` é a única marca que o RAGX carrega no próprio caminho, e é
 * suficiente: tudo que não tem esse prefixo veio do repositório aberto. Sem
 * esta distinção na tela, um resultado de fonte compartilhada parece um
 * arquivo do projeto — e a pessoa vai procurá-lo no repositório.
 */
export function origemDe(caminho: string): { base: boolean; fonte?: string } {
  if (!caminho.startsWith('@base/')) return { base: false };
  return { base: true, fonte: caminho.split('/')[1] };
}

export function MarcaOrigem({ caminho, projeto }: { caminho: string; projeto?: string }) {
  const o = origemDe(caminho);
  if (!o.base) {
    return projeto ? (
      <Badge tone="neutral" title="Outro projeto do hub">
        {projeto}
      </Badge>
    ) : null;
  }
  return (
    <Badge tone="info" title="Conhecimento base compartilhado, fora deste repositório">
      @base/{o.fonte}
    </Badge>
  );
}

// ── Overview ────────────────────────────────────────────────────────────
export function Overview({ onGo, amplo }: { onGo: (p: string) => void; amplo: boolean }) {
  const [estado, recarregar] = usePedido<KnowledgeStats>(
    () => request({ type: 'getStats' }, 'stats').then((r) => r.stats),
    [],
  );
  const [saude] = usePedido<HealthCheck[]>(
    () => request({ type: 'getHealth' }, 'health').then((r) => r.checks),
    [],
  );
  const [origens] = usePedido<SourcesOverview>(
    () => request({ type: 'getSources' }, 'sources').then((r) => r.overview),
    [],
  );

  return (
    <div className="space-y-3">
      <Quadro estado={estado} onRetry={recarregar}>
        {(s) => (
          <Grade min={amplo ? 300 : 9999}>
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
                  <Metric
                    label="Last sync"
                    value={s.lastRun.finishedAt.replace('T', ' ').replace('Z', '')}
                  />
                )}
              </div>
            </Card>

            {/* De onde vem o índice, logo na primeira tela. Sem isto, saber que
                metade do conhecimento é de uma fonte base exige procurar. */}
            {origens.fase === 'ready' && (
              <Card
                title="Origens"
                action={
                  <Button variant="ghost" onClick={() => onGo('sources')}>
                    Detalhar
                  </Button>
                }
              >
                {origens.dado.sources.map((f) => (
                  <div key={f.id} className="flex items-baseline justify-between gap-2 py-0.5">
                    <span className="truncate">
                      {f.name}{' '}
                      {f.kind === 'base' && (
                        <Badge tone={f.declared ? 'info' : 'warn'}>@base</Badge>
                      )}
                      {f.kind === 'peer' && <Badge>hub</Badge>}
                    </span>
                    <span className="font-mono tabular-nums text-fg-muted shrink-0">
                      {f.documents !== undefined ? fmt(f.documents) : '—'}
                    </span>
                  </div>
                ))}
              </Card>
            )}

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
          </Grade>
        )}
      </Quadro>

      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => onGo('search')}>
          Buscar conhecimento
        </Button>
        <Button onClick={() => onGo('graph')}>Explorar grafo</Button>
        <Button onClick={() => onGo('tasks')}>Tarefas</Button>
        <Button onClick={() => onGo('context')}>Montar contexto</Button>
      </div>
    </div>
  );
}

// ── Search ──────────────────────────────────────────────────────────────
export function Search({
  settings,
  consultaInicial,
  escopoInicial,
  prefixoInicial,
  amplo,
  onEntity,
}: {
  settings: UiSettings;
  consultaInicial?: string;
  escopoInicial?: string;
  prefixoInicial?: string;
  amplo: boolean;
  onEntity: (nome: string) => void;
}) {
  const [texto, setTexto] = useState(consultaInicial ?? '');
  const [modo, setModo] = useState<SearchMode>(settings.searchMode);
  const [abrirFiltros, setAbrirFiltros] = useState(Boolean(prefixoInicial));
  const [lang, setLang] = useState('');
  const [kind, setKind] = useState('');
  const [escopo, setEscopo] = useState(escopoInicial ?? 'current');
  const [prefixo, setPrefixo] = useState(prefixoInicial ?? '');
  const [selecionado, setSelecionado] = useState<SearchHit>();
  const consulta = useDebounced(texto, 350);

  useEffect(() => {
    if (consultaInicial) setTexto(consultaInicial);
  }, [consultaInicial]);
  useEffect(() => {
    if (escopoInicial) setEscopo(escopoInicial);
  }, [escopoInicial]);
  useEffect(() => {
    if (prefixoInicial !== undefined) {
      setPrefixo(prefixoInicial);
      setAbrirFiltros(Boolean(prefixoInicial));
    }
  }, [prefixoInicial]);

  const [origens] = usePedido<SourcesOverview>(
    () => request({ type: 'getSources' }, 'sources').then((r) => r.overview),
    [],
  );
  const escopos = useMemo(() => {
    const base = [{ id: 'current', label: 'Este projeto' }];
    if (origens.fase !== 'ready') return base;
    const pares = origens.dado.sources.filter((f) => f.kind === 'peer');
    if (!pares.length) return base;
    return [
      ...base,
      { id: 'all', label: 'Todos os projetos' },
      ...pares.map((p) => ({ id: p.scope ?? `project:${p.name}`, label: p.name })),
    ];
  }, [origens]);

  const [estado, recarregar] = usePedido<SearchResponse>(
    () =>
      request(
        {
          type: 'search',
          query: consulta,
          mode: modo,
          limit: amplo ? 50 : 30,
          filters: {
            lang: lang || undefined,
            kind: kind || undefined,
            pathGlob: prefixo || undefined,
            scope: escopo,
          },
        },
        'search',
      ).then((r) => r.response),
    [consulta, modo, lang, kind, escopo, prefixo, amplo],
    consulta.trim().length >= 2,
  );

  // Trocar de consulta invalida a seleção: manter o painel aberto com o
  // resultado da busca anterior é mostrar uma resposta para outra pergunta.
  useEffect(() => setSelecionado(undefined), [consulta, modo, escopo, prefixo]);

  const controles = (
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
        {escopos.length > 1 && (
          <label className="text-[0.9em] text-fg-muted flex items-center gap-1">
            Escopo
            <select
              value={escopo}
              onChange={(e) => setEscopo(e.target.value)}
              aria-label="Escopo da busca"
              className="bg-bg-input text-fg-input border border-border-input rounded px-1 py-0.5"
            >
              {escopos.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <Button variant="ghost" onClick={() => setAbrirFiltros(!abrirFiltros)}>
          Filtros {abrirFiltros ? '▾' : '▸'}
        </Button>
      </div>

      {abrirFiltros && (
        <div className="grid grid-cols-2 gap-2 p-2 border border-border rounded">
          <label className="text-[0.9em] text-fg-muted">
            Linguagem
            <Input
              label="Filtrar por linguagem"
              value={lang}
              onChange={setLang}
              placeholder="python"
            />
          </label>
          <label className="text-[0.9em] text-fg-muted">
            Tipo
            <Input label="Filtrar por tipo" value={kind} onChange={setKind} placeholder="function" />
          </label>
          <label className="text-[0.9em] text-fg-muted col-span-2">
            Caminho — use <code>@base/nome/</code> para ficar só numa fonte base
            <Input
              label="Filtrar por caminho"
              value={prefixo}
              onChange={setPrefixo}
              placeholder="src/ ou @base/agents/"
            />
          </label>
          <div className="col-span-2">
            <Button
              onClick={() => {
                setLang('');
                setKind('');
                setPrefixo('');
              }}
            >
              Limpar filtros
            </Button>
          </div>
        </div>
      )}
    </div>
  );

  if (consulta.trim().length < 2) {
    return (
      <div className="space-y-2">
        {controles}
        <EmptyState
          title="Busque no conhecimento do projeto"
          hints={[
            'Faça uma pergunta em linguagem natural',
            'Ou procure por um símbolo específico',
            'Híbrida combina sentido e palavra literal',
            'O escopo separa este projeto do que veio de fora',
          ]}
        />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {controles}
      <Split
        amplo={amplo}
        larguraLado={480}
        lado={
          selecionado && (
            <PainelDoResultado
              hit={selecionado}
              onFechar={() => setSelecionado(undefined)}
              onEntity={onEntity}
            />
          )
        }
        principal={
          <Quadro estado={estado} onRetry={recarregar} vazio={(r) => r.results.length === 0}>
            {(r) => (
              <div className="space-y-1">
                <p className="text-fg-muted text-[0.85em]">
                  {r.results.length} resultado(s) · {r.mode}
                  {escopo !== 'current' ? ` · escopo ${escopo}` : ''}
                  {r.degraded ? ` · degradado: ${r.degraded}` : ''}
                </p>
                {r.results.map((h) => (
                  <Resultado
                    key={h.chunkId}
                    hit={h}
                    compacto={amplo}
                    ativo={selecionado?.chunkId === h.chunkId}
                    onSelect={() => setSelecionado(h)}
                    onEntity={onEntity}
                  />
                ))}
              </div>
            )}
          </Quadro>
        }
      />

      {estado.fase === 'ready' && estado.dado.results.length === 0 && (
        <EmptyState
          title="Nenhum conhecimento encontrado"
          hints={[
            'Tente uma busca mais ampla',
            'Ou outra formulação da pergunta',
            'Remova os filtros',
            escopo === 'current'
              ? 'Amplie o escopo para incluir outros projetos'
              : 'Reduza o escopo para este projeto',
          ]}
          action={
            <Button
              onClick={() => {
                setLang('');
                setKind('');
                setPrefixo('');
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

function Resultado({
  hit,
  compacto,
  ativo,
  onSelect,
  onEntity,
}: {
  hit: SearchHit;
  /** Em tela cheia o trecho vai para o painel lateral; aqui basta a linha. */
  compacto: boolean;
  ativo: boolean;
  onSelect: () => void;
  onEntity: (n: string) => void;
}) {
  const [aberto, setAberto] = useState(false);
  const pct = Math.round(Math.min(1, hit.score * 10) * 100);
  const literal = hit.matchedBy.includes('keyword');

  return (
    <article
      className={`border rounded hover:bg-hover ${ativo ? 'border-focus' : 'border-border'}`}
    >
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
              onClick={onSelect}
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
            <MarcaOrigem
              caminho={hit.documentPath}
              projeto={
                hit.project && hit.project !== 'current' && hit.project !== 'project'
                  ? hit.project
                  : undefined
              }
            />
          </div>
          {hit.headingPath && (
            <p className="text-fg-muted text-[0.85em] truncate">{hit.headingPath}</p>
          )}
          {!compacto && (
            <pre className="mt-1 text-[0.9em] font-mono whitespace-pre-wrap break-words text-fg-muted">
              {aberto ? hit.content : hit.content.slice(0, 220)}
              {!aberto && hit.content.length > 220 ? '…' : ''}
            </pre>
          )}
          <div className="flex gap-1 mt-1">
            {!compacto && hit.content.length > 220 && (
              <Button variant="ghost" onClick={() => setAberto(!aberto)}>
                {aberto ? 'Menos' : 'Mais'}
              </Button>
            )}
            <Button variant="ghost" onClick={onSelect}>
              Ver trecho
            </Button>
            <Button
              variant="ghost"
              onClick={() =>
                send({
                  type: 'openFile',
                  path: hit.documentPath,
                  line: hit.lines[0],
                  endLine: hit.lines[1],
                })
              }
            >
              Abrir
            </Button>
            {hit.symbol && (
              <Button variant="ghost" onClick={() => onEntity(hit.symbol!)}>
                Ver no grafo
              </Button>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

/**
 * O trecho inteiro, com numeração — não o recorte de 220 caracteres.
 *
 * A busca devolve um pedaço para caber na lista. Ler de verdade exige o chunk
 * completo, e é isso que `get_chunk` serve. Em tela estreita este painel vai
 * para cima da lista; em tela cheia, para o lado.
 */
function PainelDoResultado({
  hit,
  onFechar,
  onEntity,
}: {
  hit: SearchHit;
  onFechar: () => void;
  onEntity: (n: string) => void;
}) {
  const [estado, recarregar] = usePedido<ChunkInfo>(
    () => request({ type: 'getChunk', chunkId: hit.chunkId }, 'chunk').then((r) => r.chunk),
    [hit.chunkId],
  );

  return (
    <Card
      title={hit.documentPath.split('/').pop() ?? hit.documentPath}
      action={
        <Button variant="ghost" onClick={onFechar}>
          Fechar
        </Button>
      }
    >
      <div className="flex items-center gap-1.5 flex-wrap mb-2">
        <MarcaOrigem caminho={hit.documentPath} />
        <Badge>{hit.kind}</Badge>
        {hit.symbol && <Badge tone="info">{hit.symbol}</Badge>}
      </div>
      <p className="text-fg-muted text-[0.85em] break-all mb-2">
        {hit.documentPath}:{hit.lines[0]}–{hit.lines[1]}
      </p>

      <Quadro estado={estado} onRetry={recarregar}>
        {(c) => (
          <>
            <div className="border border-border rounded p-2 overflow-x-auto max-h-[60vh] overflow-y-auto">
              <Codigo texto={c.content ?? hit.content} inicio={c.lines[0] || hit.lines[0]} />
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              <Button
                variant="primary"
                onClick={() =>
                  send({
                    type: 'openFile',
                    path: hit.documentPath,
                    line: hit.lines[0],
                    endLine: hit.lines[1],
                  })
                }
              >
                Abrir no editor
              </Button>
              <Button onClick={() => send({ type: 'copy', text: c.content ?? hit.content })}>
                Copiar
              </Button>
              {hit.symbol && <Button onClick={() => onEntity(hit.symbol!)}>Ver no grafo</Button>}
            </div>
            {c.tokens > 0 && (
              <p className="text-fg-muted text-[0.85em] mt-2">{fmt(c.tokens)} tokens</p>
            )}
          </>
        )}
      </Quadro>
    </Card>
  );
}

// ── Graph ───────────────────────────────────────────────────────────────
export function Graph({
  settings,
  entidadeInicial,
  amplo,
}: {
  settings: UiSettings;
  entidadeInicial?: string;
  amplo: boolean;
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
    () => request({ type: 'getEntity', name: selecionado!.name }, 'entity').then((r) => r.entity),
    [selecionado?.name],
    Boolean(selecionado),
  );

  /** Expansão progressiva: carrega os vizinhos DAQUELE nó e funde (§12). */
  const expandir = useCallback(
    async (n: GraphNode) => {
      try {
        const r = await request({ type: 'getGraph', entity: n.name, depth: 1 }, 'graph');
        setAcumulado((atual) => fundir(atual, r.graph, settings.maxVisibleNodes, n.id));
      } catch {
        /* falha de expansão não desmonta o que já está na tela */
      }
    },
    [settings.maxVisibleNodes],
  );

  const abrirFonte = useCallback((n: GraphNode) => {
    if (n.documentPath) send({ type: 'openFile', path: n.documentPath, line: 1 });
  }, []);

  const controles = (
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
        {acumulado.nodes.length > 0 && (
          <Button variant="ghost" onClick={() => setAcumulado({ nodes: [], edges: [] })}>
            Limpar expansões
          </Button>
        )}
        <span className="ml-auto">máx. {settings.maxVisibleNodes} nós visíveis</span>
      </label>
    </div>
  );

  if (!entidade) {
    return (
      <div className="space-y-2">
        {controles}
        <EmptyState
          title="Sem dados de grafo"
          hints={[
            'Digite o nome de uma entidade para explorar as relações dela.',
            'A cor indica o tipo; o tamanho, quantas relações o nó tem.',
            'Duplo clique carrega os vizinhos daquele nó.',
          ]}
        />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {controles}
      <Split
        amplo={amplo}
        larguraLado={340}
        lado={
          selecionado &&
          detalhe.fase === 'ready' && (
            <Card
              title={detalhe.dado.entity.name}
              action={
                <Button variant="ghost" onClick={() => setSelecionado(undefined)}>
                  Fechar
                </Button>
              }
            >
              <div className="flex items-center gap-1.5 flex-wrap mb-2">
                <Badge tone="info">{detalhe.dado.entity.type}</Badge>
                {detalhe.dado.entity.documentPath && (
                  <MarcaOrigem caminho={detalhe.dado.entity.documentPath} />
                )}
              </div>
              {detalhe.dado.entity.qualifiedName && (
                <p className="font-mono text-[0.85em] text-fg-muted break-all mb-1">
                  {detalhe.dado.entity.qualifiedName}
                </p>
              )}
              {detalhe.dado.entity.summary && (
                <p className="text-fg-muted text-[0.9em] mt-1">{detalhe.dado.entity.summary}</p>
              )}
              {detalhe.dado.relations.length > 0 && (
                <div className="mt-2">
                  <p className="font-semibold text-[0.9em] mb-1">
                    Relações ({detalhe.dado.relations.length})
                  </p>
                  <ul className="text-[0.9em] space-y-0.5 max-h-56 overflow-y-auto">
                    {detalhe.dado.relations.slice(0, 60).map((r, i) => (
                      <li key={i}>
                        <button
                          type="button"
                          onClick={() => {
                            setBusca(r.target);
                            setEntidade(r.target);
                          }}
                          className="font-mono text-left hover:underline text-fg-muted
                                     hover:text-link w-full truncate"
                        >
                          {r.direction === 'out' ? '→' : '←'} {r.type} {r.target}
                        </button>
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
                      className="block text-link hover:underline text-[0.9em] text-left truncate w-full"
                    >
                      {s.path}
                      {s.line ? `:${s.line}` : ''}
                    </button>
                  ))}
                </div>
              )}
            </Card>
          )
        }
        principal={
          <Quadro estado={estado} onRetry={recarregar}>
            {() => (
              <GraphView
                graph={acumulado}
                center={acumulado.nodes.find((n) => n.name === entidade)?.id}
                selectedId={selecionado?.id}
                onSelect={setSelecionado}
                onExpand={(n) => void expandir(n)}
                onOpen={abrirFonte}
                // Em tela cheia o grafo usa a altura da janela: o mesmo
                // desenho em 360px vira um novelo, e em 640px se lê.
                height={amplo ? Math.max(420, Math.round(window.innerHeight * 0.62)) : 360}
              />
            )}
          </Quadro>
        }
      />
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
export function Dictionary({ onEntity }: { onEntity: (n: string) => void; amplo?: boolean }) {
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
/**
 * Os arquivos indexados, separados por origem.
 *
 * O filtro por origem existe porque a lista misturada não responde à pergunta
 * que as pessoas fazem aqui: "o que deste índice é meu repositório?". Com
 * fontes base ativas, metade da lista pode vir de fora — e parecer sua.
 */
export function Documents({
  caminhoInicial,
  prefixoInicial,
  amplo,
}: {
  caminhoInicial?: string;
  prefixoInicial?: string;
  amplo: boolean;
}) {
  const [busca, setBusca] = useState(prefixoInicial ?? '');
  const consulta = useDebounced(busca, 350);
  const [selecionado, setSelecionado] = useState<string | undefined>(caminhoInicial);
  const [origem, setOrigem] = useState<string>(
    prefixoInicial ? `base:${prefixoInicial}` : 'todas',
  );

  useEffect(() => {
    if (caminhoInicial) setSelecionado(caminhoInicial);
  }, [caminhoInicial]);
  useEffect(() => {
    if (prefixoInicial) {
      setBusca(prefixoInicial);
      setOrigem(`base:${prefixoInicial}`);
    }
  }, [prefixoInicial]);

  const [origens] = usePedido<SourcesOverview>(
    () => request({ type: 'getSources' }, 'sources').then((r) => r.overview),
    [],
  );

  const [lista, recarregarLista] = usePedido<DocumentInfo[]>(
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

  const basesInstaladas =
    origens.fase === 'ready'
      ? origens.dado.sources.filter((f) => f.kind === 'base' && f.declared)
      : [];

  const filtrar = (docs: DocumentInfo[]) => {
    if (origem === 'todas') return docs;
    if (origem === 'projeto') return docs.filter((d) => !d.path.startsWith('@base/'));
    const prefixo = origem.slice('base:'.length);
    return docs.filter((d) => d.path.startsWith(prefixo));
  };

  const detalhe = selecionado && (
    <Card
      title={selecionado.split('/').pop() ?? selecionado}
      action={
        <Button variant="ghost" onClick={() => setSelecionado(undefined)}>
          Fechar
        </Button>
      }
    >
      <div className="flex items-center gap-1.5 flex-wrap mb-2">
        <MarcaOrigem caminho={selecionado} />
      </div>
      <p className="text-fg-muted text-[0.85em] break-all mb-2">{selecionado}</p>

      <Quadro estado={conhecimento} onRetry={recarregarConhecimento}>
        {(k) =>
          k.indexed ? (
            <>
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <Badge tone="ok">✓ indexado</Badge>
                <Badge>{k.chunks.length} chunks</Badge>
                {k.document?.lang && <Badge>{k.document.lang}</Badge>}
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
              {k.chunks.length > 0 && (
                <div className="mb-2">
                  <p className="text-fg-muted text-[0.9em] mb-0.5">Chunks</p>
                  <ul className="text-[0.85em] font-mono space-y-0.5 max-h-52 overflow-y-auto">
                    {k.chunks.map((c) => (
                      <li key={c.chunkId}>
                        <button
                          type="button"
                          onClick={() =>
                            send({
                              type: 'openFile',
                              path: k.path,
                              line: c.lines[0],
                              endLine: c.lines[1],
                            })
                          }
                          className="w-full text-left truncate hover:underline text-fg-muted
                                     hover:text-link"
                        >
                          L{c.lines[0]}–{c.lines[1]} {c.symbol || c.headingPath || c.kind}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Button onClick={() => send({ type: 'openFile', path: k.path, line: 1 })} variant="primary">
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
  );

  return (
    <div className="space-y-2">
      <Input
        label="Filtrar documentos"
        value={busca}
        onChange={setBusca}
        placeholder="filtrar por caminho…"
      />

      {basesInstaladas.length > 0 && (
        <div className="flex gap-1 flex-wrap">
          {[
            { id: 'todas', label: 'Todas as origens' },
            { id: 'projeto', label: 'Só este projeto' },
            ...basesInstaladas.map((f) => ({
              id: `base:${f.pathPrefix}`,
              label: `@base/${f.name}`,
            })),
          ].map((o) => (
            <button
              key={o.id}
              type="button"
              aria-pressed={origem === o.id}
              onClick={() => setOrigem(o.id)}
              className={`px-2 py-0.5 rounded text-[0.85em] border ${
                origem === o.id ? 'border-focus bg-active-soft' : 'border-border hover:bg-hover'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}

      <Split
        amplo={amplo}
        lado={detalhe}
        principal={
          <Quadro estado={lista} onRetry={recarregarLista} vazio={(d) => d.length === 0}>
            {(docs) => {
              const visiveis = filtrar(docs);
              if (!visiveis.length) {
                return (
                  <EmptyState
                    title="Nenhum documento nesta origem"
                    hints={['Troque a origem ou limpe o filtro de caminho.']}
                    action={<Button onClick={() => setOrigem('todas')}>Ver todas</Button>}
                  />
                );
              }
              return (
                <>
                  <p className="text-fg-muted text-[0.85em]">
                    {visiveis.length} de {docs.length} documento(s)
                  </p>
                  <VirtualList
                    items={visiveis}
                    itemHeight={30}
                    height={Math.min(amplo ? 640 : 420, visiveis.length * 30 + 4)}
                    render={(d) => (
                      <button
                        type="button"
                        onClick={() => setSelecionado(d.path)}
                        className={`w-full flex items-center gap-2 px-2 py-1 text-left rounded
                                    hover:bg-hover ${
                                      d.path === selecionado ? 'bg-active-soft' : ''
                                    }`}
                      >
                        {d.path.startsWith('@base/') && (
                          <span
                            aria-hidden
                            title="conhecimento base"
                            className="shrink-0 w-1.5 h-1.5 rounded-full bg-info"
                          />
                        )}
                        <span className="truncate">{d.path}</span>
                        <span className="ml-auto text-fg-muted font-mono text-[0.85em] shrink-0">
                          {d.chunks}
                        </span>
                      </button>
                    )}
                  />
                </>
              );
            }}
          </Quadro>
        }
      />
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
export function Monitor({ amplo }: { amplo: boolean }) {
  const [estado, recarregar] = usePedido<MonitorSnapshot>(
    () => request({ type: 'getMonitor' }, 'monitor').then((r) => r.monitor),
    [],
  );

  return (
    <Quadro estado={estado} onRetry={recarregar}>
      {(m) => (
        <Grade min={amplo ? 300 : 9999}>
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
        </Grade>
      )}
    </Quadro>
  );
}

// ── Security ────────────────────────────────────────────────────────────
export function Security({ amplo }: { amplo: boolean }) {
  const [estado, recarregar] = usePedido<SecurityStatus>(
    () => request({ type: 'getSecurity' }, 'security').then((r) => r.security),
    [],
  );

  return (
    <Quadro estado={estado} onRetry={recarregar}>
      {(s) => (
        <Grade min={amplo ? 300 : 9999}>
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
        </Grade>
      )}
    </Quadro>
  );
}

// ── Agents ──────────────────────────────────────────────────────────────
export function Agents({ amplo }: { amplo: boolean }) {
  const [estado, recarregar] = usePedido<AgentInfo[]>(
    () => request({ type: 'getAgents' }, 'agents').then((r) => r.agents),
    [],
  );

  return (
    <Quadro estado={estado} onRetry={recarregar} vazio={(a) => a.length === 0}>
      {(agentes) => (
        <Grade min={amplo ? 280 : 9999}>
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
        </Grade>
      )}
    </Quadro>
  );
}
