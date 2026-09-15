/**
 * Origens do conhecimento — de onde veio cada coisa no índice.
 *
 * Esta tela existe porque o índice do RAGX pode conter três coisas ao mesmo
 * tempo, e confundi-las tem consequência prática:
 *
 *   - o REPOSITÓRIO aberto, que o RAGX indexa e reindexa;
 *   - fontes BASE (`@base/<nome>/…`), compartilhadas entre projetos da
 *     máquina, versionadas em outro lugar — editar o arquivo daqui não muda
 *     nada nelas;
 *   - outros PROJETOS do hub, que podem nem estar clonados; o que se sabe
 *     deles é a superfície pública que publicaram.
 *
 * Mostrar tudo como "conhecimento do projeto" faz a pessoa procurar no
 * repositório um arquivo que nunca esteve lá.
 */

import { useState } from 'react';

import type { KnowledgeSource, SourcesOverview } from '../../../src/rag/types';
import { request, send } from '../bridge';
import { Badge, Button, Card, Grade, Metric, Split, fmt } from '../components';
import { Quadro, usePedido } from './estado';

const ROTULOS: Record<KnowledgeSource['kind'], string> = {
  project: 'Este projeto',
  base: 'Conhecimento base',
  peer: 'Outros projetos (hub)',
};

export function Sources({
  amplo,
  onBuscar,
  onDocumentos,
}: {
  amplo: boolean;
  /** Buscar restrito a uma origem. */
  onBuscar: (escopo: string, prefixo?: string) => void;
  /** Listar os documentos de uma origem. */
  onDocumentos: (prefixo: string) => void;
}) {
  const [estado, recarregar] = usePedido<SourcesOverview>(
    () => request({ type: 'getSources' }, 'sources').then((r) => r.overview),
    [],
  );
  const [selecionada, setSelecionada] = useState<string>();

  return (
    <Quadro estado={estado} onRetry={recarregar}>
      {(o) => {
        const escolhida = o.sources.find((s) => s.id === selecionada);
        const porTipo = agrupar(o.sources);

        return (
          <Split
            amplo={amplo}
            lado={
              escolhida && (
                <Detalhe
                  fonte={escolhida}
                  onFechar={() => setSelecionada(undefined)}
                  onBuscar={onBuscar}
                  onDocumentos={onDocumentos}
                />
              )
            }
            principal={
              <div className="space-y-3">
                {(['project', 'base', 'peer'] as const).map((tipo) => {
                  const fontes = porTipo.get(tipo) ?? [];
                  if (!fontes.length) return null;
                  return (
                    <section key={tipo}>
                      <h2 className="font-semibold text-[0.95em] mb-1">
                        {ROTULOS[tipo]}{' '}
                        <span className="text-fg-muted font-normal">({fontes.length})</span>
                      </h2>
                      <Grade min={amplo ? 260 : 999}>
                        {fontes.map((f) => (
                          <Cartao
                            key={f.id}
                            fonte={f}
                            ativa={f.id === selecionada}
                            onClick={() => setSelecionada(f.id === selecionada ? undefined : f.id)}
                          />
                        ))}
                      </Grade>
                    </section>
                  );
                })}

                {porTipo.get('base')?.some((f) => !f.declared) && (
                  <p className="text-fg-muted text-[0.85em]">
                    Fonte instalada na máquina mas não declarada por este projeto
                    NÃO entra neste índice. Declare em <code>[base] sources</code>{' '}
                    no <code>ragx.toml</code> e rode <code>ragx base sync</code>.
                  </p>
                )}

                {o.integrations.length > 0 && (
                  <Card title="Integrações entre projetos">
                    <ul className="text-[0.9em] space-y-0.5">
                      {o.integrations.slice(0, 40).map((i, n) => (
                        <li key={n} className="font-mono text-fg-muted">
                          {i.from} → {i.to}
                          <span className="ml-1 text-[0.9em]">
                            ({i.kind}
                            {i.name ? ` ${i.name}` : ''})
                          </span>
                        </li>
                      ))}
                    </ul>
                  </Card>
                )}

                {(o.unresolved.length > 0 || o.divergences.length > 0) && (
                  <Card title="Pendências do hub">
                    {o.unresolved.length > 0 && (
                      <>
                        <p className="text-fg-muted text-[0.9em] mb-1">
                          Consumos sem provedor conhecido
                        </p>
                        <ul className="text-[0.9em] space-y-0.5 mb-2">
                          {o.unresolved.slice(0, 20).map((u) => (
                            <li key={u} className="font-mono text-warn">
                              {u}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                    {o.divergences.length > 0 && (
                      <>
                        <p className="text-fg-muted text-[0.9em] mb-1">Divergências de contrato</p>
                        <ul className="text-[0.9em] space-y-0.5">
                          {o.divergences.slice(0, 20).map((d) => (
                            <li key={d} className="text-err">
                              {d}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </Card>
                )}

                <div className="flex flex-wrap gap-2">
                  <Button onClick={recarregar}>Atualizar</Button>
                  <Button variant="ghost" onClick={() => send({ type: 'sync' })}>
                    Sincronizar índice
                  </Button>
                </div>
              </div>
            }
          />
        );
      }}
    </Quadro>
  );
}

function agrupar(fontes: KnowledgeSource[]): Map<KnowledgeSource['kind'], KnowledgeSource[]> {
  const mapa = new Map<KnowledgeSource['kind'], KnowledgeSource[]>();
  for (const f of fontes) {
    const atual = mapa.get(f.kind) ?? [];
    atual.push(f);
    mapa.set(f.kind, atual);
  }
  return mapa;
}

function Cartao({
  fonte,
  ativa,
  onClick,
}: {
  fonte: KnowledgeSource;
  ativa: boolean;
  onClick: () => void;
}) {
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
        <span className="font-semibold truncate">{fonte.name}</span>
        <Marcas fonte={fonte} />
      </div>
      {fonte.origin && (
        <p className="text-fg-muted text-[0.85em] truncate mt-0.5" title={fonte.origin}>
          {fonte.origin}
        </p>
      )}
      <div className="mt-1 text-[0.85em] text-fg-muted font-mono">
        {/* `undefined` não vira zero: zero é uma afirmação sobre o índice, e
            "não sei" é a verdade quando o projeto nem está clonado. */}
        {fonte.documents !== undefined
          ? `${fmt(fonte.documents)} arquivo(s)`
          : 'contagem indisponível'}
        {fonte.chunks !== undefined ? ` · ${fmt(fonte.chunks)} chunks` : ''}
      </div>
    </button>
  );
}

function Marcas({ fonte }: { fonte: KnowledgeSource }) {
  return (
    <>
      {fonte.kind === 'base' && (
        <Badge tone={fonte.declared ? 'info' : 'warn'}>
          {fonte.declared ? '@base · em uso' : '@base · não declarada'}
        </Badge>
      )}
      {fonte.kind === 'base' && !fonte.enabled && <Badge tone="warn">desativada</Badge>}
      {fonte.kind === 'peer' && (
        <Badge tone={fonte.cloned ? 'ok' : 'neutral'}>
          {fonte.cloned ? 'clonado' : 'só federação'}
        </Badge>
      )}
      {fonte.kind === 'peer' && fonte.status && fonte.status !== 'ok' && (
        <Badge tone="warn">{fonte.status}</Badge>
      )}
      {fonte.kind === 'project' && <Badge tone="ok">indexado aqui</Badge>}
    </>
  );
}

function Detalhe({
  fonte,
  onFechar,
  onBuscar,
  onDocumentos,
}: {
  fonte: KnowledgeSource;
  onFechar: () => void;
  onBuscar: (escopo: string, prefixo?: string) => void;
  onDocumentos: (prefixo: string) => void;
}) {
  return (
    <Card
      title={fonte.name}
      action={
        <Button variant="ghost" onClick={onFechar}>
          Fechar
        </Button>
      }
    >
      <div className="flex flex-wrap gap-1 mb-2">
        <Marcas fonte={fonte} />
      </div>

      <Metric label="Tipo" value={ROTULOS[fonte.kind]} />
      {fonte.origin && <Metric label="Origem" value={<span className="break-all">{fonte.origin}</span>} />}
      {fonte.commit && <Metric label="Commit" value={fonte.commit.slice(0, 8)} />}
      {fonte.path && <Metric label="Caminho" value={<span className="break-all">{fonte.path}</span>} />}
      {fonte.visibility && <Metric label="Visibilidade" value={fonte.visibility} />}
      <Metric
        label="Arquivos"
        value={fonte.documents !== undefined ? fmt(fonte.documents) : '—'}
      />
      {fonte.chunks !== undefined && <Metric label="Chunks" value={fmt(fonte.chunks)} />}
      {fonte.entities !== undefined && <Metric label="Entidades" value={fmt(fonte.entities)} />}

      <div className="flex flex-wrap gap-2 mt-3">
        {fonte.scope && (
          <Button variant="primary" onClick={() => onBuscar(fonte.scope!, fonte.pathPrefix)}>
            Buscar só aqui
          </Button>
        )}
        {fonte.pathPrefix && (
          <>
            <Button onClick={() => onDocumentos(fonte.pathPrefix!)}>Ver os arquivos</Button>
            <Button variant="ghost" onClick={() => onBuscar('current', fonte.pathPrefix)}>
              Buscar neste prefixo
            </Button>
          </>
        )}
      </div>

      <p className="text-fg-muted text-[0.85em] mt-3">{explicar(fonte)}</p>
    </Card>
  );
}

function explicar(f: KnowledgeSource): string {
  if (f.kind === 'project') {
    return 'O repositório aberto. É o único conhecimento que o `sync` deste projeto atualiza.';
  }
  if (f.kind === 'base') {
    return f.declared
      ? 'Instalada nesta máquina e declarada por este projeto: os documentos entram ' +
          'no índice com o prefixo @base/. Os arquivos vivem fora do repositório — ' +
          'para mudá-los, mude a fonte de origem.'
      : 'Instalada nesta máquina, mas NÃO declarada por este projeto. Nada dela entra ' +
          'neste índice. Isso é proposital: instalar uma fonte não pode mudar em ' +
          'silêncio o índice de todos os projetos da máquina.';
  }
  return f.cloned
    ? 'Projeto registrado no hub e presente em disco. A busca com escopo nele lê o ' +
        'índice dele, não o deste projeto.'
    : 'Projeto registrado no hub sem cópia local. O que se sabe dele é a superfície ' +
        'pública que publicou — rotas, eventos e clientes, não o código.';
}
