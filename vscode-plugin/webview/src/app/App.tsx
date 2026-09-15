/**
 * A casca: navegação lateral, barra de estado e a página ativa.
 *
 * Três larguras, não duas (§31):
 *
 *   - **compacta** (<520px): navegação vira menu. É o painel lateral apertado.
 *   - **normal** (520–1099px): navegação fixa com rótulo, uma coluna.
 *   - **ampla** (≥1100px): as páginas ganham uma segunda coluna de detalhe.
 *
 * A decisão é pela LARGURA MEDIDA, não pela hospedagem: uma barra lateral
 * arrastada até a metade da tela merece o mesmo layout da aba do editor. A
 * hospedagem só decide se faz sentido oferecer "abrir em tela cheia".
 */

import { useEffect, useState } from 'react';

import type { HostMode, PageId, UiSettings } from '../../../src/protocol';
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
  Sources,
  Tasks,
} from '../pages';

const PAGINAS: Array<{ id: PageId; label: string; icone: string; grupo: 1 | 2 | 3 }> = [
  { id: 'overview', label: 'Overview', icone: '◱', grupo: 1 },
  { id: 'search', label: 'Search', icone: '⌕', grupo: 1 },
  { id: 'graph', label: 'Graph', icone: '◈', grupo: 1 },
  { id: 'dictionary', label: 'Dictionary', icone: '☰', grupo: 1 },
  { id: 'documents', label: 'Documents', icone: '▤', grupo: 2 },
  { id: 'sources', label: 'Origens', icone: '⛁', grupo: 2 },
  { id: 'context', label: 'Context', icone: '◫', grupo: 2 },
  { id: 'tasks', label: 'Tasks', icone: '☑', grupo: 3 },
  { id: 'agents', label: 'Agents', icone: '◇', grupo: 3 },
  { id: 'monitor', label: 'Monitor', icone: '◉', grupo: 3 },
  { id: 'security', label: 'Security', icone: '⚿', grupo: 3 },
];

const PADRAO: UiSettings = {
  searchMode: 'hybrid',
  graphMaxDepth: 2,
  maxVisibleNodes: 120,
  contextTokenBudget: 4000,
};

const COMPACTO = 520;
const AMPLO = 1100;

export function App() {
  const [pagina, setPagina] = useState<PageId>(restore<PageId>('page', 'overview'));
  const [estado, setEstado] = useState<SystemState>('disconnected');
  const [projeto, setProjeto] = useState<string>();
  const [transporte, setTransporte] = useState<string>();
  const [mensagem, setMensagem] = useState<string>();
  const [hospedagem, setHospedagem] = useState<HostMode>('sidebar');
  const [settings, setSettings] = useState<UiSettings>(PADRAO);
  const [largura, setLargura] = useState(window.innerWidth);
  const [menuAberto, setMenuAberto] = useState(false);
  const [carga, setCarga] = useState<Record<string, string>>({});

  useEffect(() => {
    const offEstado = onState((s) => {
      setEstado(s.state);
      setProjeto(s.project?.name);
      setTransporte(s.project?.transport);
      setMensagem(s.message);
      setHospedagem(s.host);
    });
    const offSettings = onSettings(setSettings);
    const offNav = onNavigate((p, payload) => {
      setPagina(p);
      // Um payload vazio tem de LIMPAR a carga anterior: sem isso, ir para
      // Search sem consulta reabriria a busca do comando anterior.
      setCarga(payload ?? {});
    });
    void request({ type: 'ready' }, 'ack').catch(() => {
      /* o host responde quando estiver pronto */
    });
    const onResize = () => setLargura(window.innerWidth);
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

  const estreito = largura < COMPACTO;
  const amplo = largura >= AMPLO;

  const irPara = (p: string, payload?: Record<string, string>) => {
    setPagina(p as PageId);
    setCarga(payload ?? {});
    setMenuAberto(false);
  };

  const noGrafo = (nome: string) => irPara('graph', { entity: nome });
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
        <h1 className="font-semibold truncate">RAGX Knowledge</h1>
        {amplo && projeto && (
          <span className="text-fg-muted truncate text-[0.9em]">· {projeto}</span>
        )}
        <div className="ml-auto flex items-center gap-1">
          {/* Só na lateral: dentro da aba do editor este botão apontaria para
              a própria tela onde já se está. */}
          {hospedagem === 'sidebar' && (
            <button
              type="button"
              aria-label="Abrir em tela cheia"
              title="Abrir em tela cheia, no editor"
              onClick={() => send({ type: 'openEditor', page: pagina })}
              className="px-1.5 hover:bg-hover rounded"
            >
              ⛶
            </button>
          )}
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
              } ${amplo ? 'w-44' : 'w-36'} shrink-0 border-r border-border p-1 overflow-y-auto`}
            >
              {PAGINAS.map((p, i) => (
                <div key={p.id}>
                  {/* Um separador entre grupos: onze itens numa lista corrida
                      viram uma parede de texto sem hierarquia nenhuma. */}
                  {i > 0 && PAGINAS[i - 1].grupo !== p.grupo && (
                    <hr className="my-1 border-border" />
                  )}
                  <button
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
                </div>
              ))}
            </nav>
          )}

          <main className="flex-1 overflow-auto p-3 min-w-0">
            {pagina === 'overview' && <Overview onGo={irPara} amplo={amplo} />}
            {pagina === 'search' && (
              <Search
                settings={settings}
                consultaInicial={carga.query}
                escopoInicial={carga.scope}
                prefixoInicial={carga.prefix}
                amplo={amplo}
                onEntity={noGrafo}
              />
            )}
            {pagina === 'graph' && (
              <Graph settings={settings} entidadeInicial={carga.entity} amplo={amplo} />
            )}
            {pagina === 'dictionary' && <Dictionary onEntity={noGrafo} amplo={amplo} />}
            {pagina === 'documents' && (
              <Documents
                caminhoInicial={carga.path}
                prefixoInicial={carga.prefix}
                amplo={amplo}
              />
            )}
            {pagina === 'sources' && (
              <Sources
                amplo={amplo}
                onBuscar={(escopo, prefixo) =>
                  irPara('search', { scope: escopo, prefix: prefixo ?? '' })
                }
                onDocumentos={(prefixo) => irPara('documents', { prefix: prefixo })}
              />
            )}
            {pagina === 'context' && <Context settings={settings} />}
            {pagina === 'tasks' && <Tasks amplo={amplo} pedidoInicial={carga.request} />}
            {pagina === 'agents' && <Agents amplo={amplo} />}
            {pagina === 'monitor' && <Monitor amplo={amplo} />}
            {pagina === 'security' && <Security amplo={amplo} />}
          </main>
        </div>
      )}

      <footer className="flex items-center gap-3 px-3 py-1 border-t border-border text-[0.85em] shrink-0">
        <Status state={estado} detail={mensagem} />
        {projeto && !amplo && <span className="text-fg-muted truncate">{projeto}</span>}
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
