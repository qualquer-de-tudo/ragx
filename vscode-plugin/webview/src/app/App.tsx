/**
 * A casca: navegação lateral, barra de estado e a página ativa.
 *
 * A navegação colapsa abaixo de 520px (§31). O painel lateral do VS Code
 * costuma ter 300px — assumir 1200 seria projetar para uma tela que quase
 * ninguém usa.
 */

import { useEffect, useState } from 'react';

import type { PageId, UiSettings } from '../../../src/protocol';
import type { SystemState } from '../../../src/rag/types';
import { onNavigate, onSettings, onState, persist, request, restore, send } from '../bridge';
import { Button, EmptyState, Status } from '../components';
import {
  Agents,
  Context,
  Dictionary,
  Documents,
  Graph,
  Monitor,
  Overview,
  Search,
  Security,
} from '../pages';

const PAGINAS: Array<{ id: PageId; label: string; icone: string }> = [
  { id: 'overview', label: 'Overview', icone: '◱' },
  { id: 'search', label: 'Search', icone: '⌕' },
  { id: 'graph', label: 'Graph', icone: '◈' },
  { id: 'dictionary', label: 'Dictionary', icone: '☰' },
  { id: 'documents', label: 'Documents', icone: '▤' },
  { id: 'context', label: 'Context', icone: '◫' },
  { id: 'agents', label: 'Agents', icone: '◇' },
  { id: 'monitor', label: 'Monitor', icone: '◉' },
  { id: 'security', label: 'Security', icone: '⚿' },
];

const PADRAO: UiSettings = {
  searchMode: 'hybrid',
  graphMaxDepth: 2,
  maxVisibleNodes: 120,
  contextTokenBudget: 4000,
};

export function App() {
  const [pagina, setPagina] = useState<PageId>(restore<PageId>('page', 'overview'));
  const [estado, setEstado] = useState<SystemState>('disconnected');
  const [projeto, setProjeto] = useState<string>();
  const [transporte, setTransporte] = useState<string>();
  const [mensagem, setMensagem] = useState<string>();
  const [settings, setSettings] = useState<UiSettings>(PADRAO);
  const [estreito, setEstreito] = useState(window.innerWidth < 520);
  const [menuAberto, setMenuAberto] = useState(false);
  const [carga, setCarga] = useState<Record<string, string>>({});

  useEffect(() => {
    const offEstado = onState((s) => {
      setEstado(s.state);
      setProjeto(s.project?.name);
      setTransporte(s.project?.transport);
      setMensagem(s.message);
    });
    const offSettings = onSettings(setSettings);
    const offNav = onNavigate((p, payload) => {
      setPagina(p);
      if (payload) setCarga(payload);
    });
    void request({ type: 'ready' }, 'ack').catch(() => {
      /* o host responde quando estiver pronto */
    });
    const onResize = () => setEstreito(window.innerWidth < 520);
    window.addEventListener('resize', onResize);
    return () => {
      offEstado();
      offSettings();
      offNav();
      window.removeEventListener('resize', onResize);
    };
  }, []);

  useEffect(() => {
    persist({ page: pagina });
  }, [pagina]);

  const irPara = (p: string) => {
    setPagina(p as PageId);
    setMenuAberto(false);
  };

  const desconectado = estado === 'disconnected' || estado === 'error';

  return (
    <div className="h-full flex flex-col">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-border shrink-0">
        {estreito && (
          <button
            type="button"
            aria-label="Menu"
            aria-expanded={menuAberto}
            onClick={() => setMenuAberto(!menuAberto)}
            className="px-1.5 hover:bg-hover rounded"
          >
            ☰
          </button>
        )}
        <h1 className="font-semibold">RAGX Knowledge</h1>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            aria-label="Configurações"
            title="Configurações"
            onClick={() => send({ type: 'openSettings' })}
            className="px-1.5 hover:bg-hover rounded"
          >
            ⚙
          </button>
          <button
            type="button"
            aria-label="Logs"
            title="Ver logs"
            onClick={() => send({ type: 'openLogs' })}
            className="px-1.5 hover:bg-hover rounded"
          >
            ⋯
          </button>
        </div>
      </header>

      {desconectado ? (
        <div className="flex-1 overflow-auto p-3">
          <SemConexao estado={estado} mensagem={mensagem} />
        </div>
      ) : (
        <div className="flex-1 flex min-h-0">
          {(!estreito || menuAberto) && (
            <nav
              aria-label="Seções"
              className={`${
                estreito ? 'absolute z-10 bg-bg-side border-r border-border h-full' : ''
              } w-36 shrink-0 border-r border-border p-1 overflow-y-auto`}
            >
              {PAGINAS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  aria-current={pagina === p.id ? 'page' : undefined}
                  onClick={() => irPara(p.id)}
                  className={`w-full flex items-center gap-2 px-2 py-1 rounded text-left
                              hover:bg-hover ${
                                pagina === p.id ? 'bg-active text-active-fg' : ''
                              }`}
                >
                  <span aria-hidden className="w-3 text-center opacity-70">
                    {p.icone}
                  </span>
                  <span className="truncate">{p.label}</span>
                </button>
              ))}
            </nav>
          )}

          <main className="flex-1 overflow-auto p-3 min-w-0">
            {pagina === 'overview' && <Overview onGo={irPara} />}
            {pagina === 'search' && (
              <Search
                settings={settings}
                consultaInicial={carga.query}
                onEntity={(nome) => {
                  setCarga({ entity: nome });
                  setPagina('graph');
                }}
              />
            )}
            {pagina === 'graph' && <Graph settings={settings} entidadeInicial={carga.entity} />}
            {pagina === 'dictionary' && (
              <Dictionary
                onEntity={(nome) => {
                  setCarga({ entity: nome });
                  setPagina('graph');
                }}
              />
            )}
            {pagina === 'documents' && <Documents caminhoInicial={carga.path} />}
            {pagina === 'context' && <Context settings={settings} />}
            {pagina === 'agents' && <Agents />}
            {pagina === 'monitor' && <Monitor />}
            {pagina === 'security' && <Security />}
          </main>
        </div>
      )}

      <footer className="flex items-center gap-3 px-3 py-1 border-t border-border text-[0.85em] shrink-0">
        <Status state={estado} detail={mensagem} />
        {projeto && <span className="text-fg-muted truncate">{projeto}</span>}
        {transporte && (
          <span className="ml-auto text-fg-muted" title="Transporte usado para falar com o RAGX">
            {transporte}
          </span>
        )}
      </footer>
    </div>
  );
}

function SemConexao({ estado, mensagem }: { estado: SystemState; mensagem?: string }) {
  if (estado === 'disconnected') {
    return (
      <EmptyState
        title="RAGX não detectado"
        hints={[
          'Não encontrei ragx.toml, knowledge/ nem .ragx/ neste workspace.',
          mensagem ?? 'Rode `ragx init` na raiz do projeto.',
        ]}
        action={
          <div className="flex flex-wrap gap-2 justify-center">
            <Button variant="primary" onClick={() => send({ type: 'reconnect' })}>
              Procurar de novo
            </Button>
            <Button onClick={() => send({ type: 'openSettings' })}>Configurar conexão</Button>
          </div>
        }
      />
    );
  }
  return (
    <EmptyState
      title="Não foi possível conectar ao RAGX"
      hints={[
        mensagem ?? 'O comando configurado não respondeu.',
        'Verifique se `ragx` está instalado e no PATH.',
      ]}
      action={
        <div className="flex flex-wrap gap-2 justify-center">
          <Button variant="primary" onClick={() => send({ type: 'reconnect' })}>
            Tentar de novo
          </Button>
          <Button onClick={() => send({ type: 'openSettings' })}>Configurações</Button>
          <Button onClick={() => send({ type: 'openLogs' })}>Ver logs</Button>
        </div>
      }
    />
  );
}
