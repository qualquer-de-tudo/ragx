/**
 * A ponte tipada com a extensão.
 *
 * Toda requisição tem `id` e vira uma Promise. Sem correlação por id, duas
 * buscas rápidas resolveriam fora de ordem e a tela mostraria o resultado da
 * consulta anterior — o bug mais irritante de UI de busca.
 */

import type {
  ExtensionMessage,
  PageId,
  ResultPayload,
  UiError,
  UiSettings,
  WebviewMessage,
} from '../../src/protocol';
import type { ProjectInfo, SystemState } from '../../src/rag/types';

interface VsCodeApi {
  postMessage(msg: unknown): void;
  getState(): unknown;
  setState(state: unknown): void;
}

declare function acquireVsCodeApi(): VsCodeApi;

const api: VsCodeApi = acquireVsCodeApi();

type Pendente = {
  resolve: (p: ResultPayload) => void;
  reject: (e: UiError) => void;
};

const pendentes = new Map<string, Pendente>();
let seq = 0;

/**
 * `Omit` sobre uma união NÃO distribui: ele colapsa para os campos comuns, e o
 * resultado aceita `{type: 'search'}` mas rejeita o `query` que vai junto. O
 * `T extends unknown` força a distribuição por membro.
 */
type SemId<T> = T extends unknown ? Omit<T, 'id'> : never;

/** Uma mensagem qualquer da webview, ainda sem o id de correlação. */
export type Saida = SemId<WebviewMessage>;

export interface HostState {
  state: SystemState;
  project?: ProjectInfo;
  message?: string;
}

type OuvinteEstado = (s: HostState) => void;
type OuvinteSettings = (s: UiSettings) => void;
type OuvinteNavegacao = (page: PageId, payload?: Record<string, string>) => void;

const ouvintesEstado = new Set<OuvinteEstado>();
const ouvintesSettings = new Set<OuvinteSettings>();
const ouvintesNavegacao = new Set<OuvinteNavegacao>();

window.addEventListener('message', (ev: MessageEvent<ExtensionMessage>) => {
  const msg = ev.data;
  if (!msg || typeof msg !== 'object') return;

  switch (msg.type) {
    case 'state':
      ouvintesEstado.forEach((f) =>
        f({ state: msg.state, project: msg.project, message: msg.message }),
      );
      return;
    case 'settings':
      ouvintesSettings.forEach((f) => f(msg.settings));
      return;
    case 'navigate':
      ouvintesNavegacao.forEach((f) => f(msg.page, msg.payload));
      return;
    case 'result': {
      const p = pendentes.get(msg.id);
      if (!p) return; // resposta de requisição já cancelada
      pendentes.delete(msg.id);
      if (msg.ok) p.resolve(msg.payload);
      else p.reject(msg.error);
      return;
    }
  }
});

export function onState(f: OuvinteEstado): () => void {
  ouvintesEstado.add(f);
  return () => ouvintesEstado.delete(f);
}

export function onSettings(f: OuvinteSettings): () => void {
  ouvintesSettings.add(f);
  return () => ouvintesSettings.delete(f);
}

export function onNavigate(f: OuvinteNavegacao): () => void {
  ouvintesNavegacao.add(f);
  return () => ouvintesNavegacao.delete(f);
}

/** Envia e espera a resposta correspondente. */
export function request<K extends ResultPayload['kind']>(
  msg: Saida,
  kind: K,
): Promise<Extract<ResultPayload, { kind: K }>> {
  const id = `r${++seq}`;
  return new Promise((resolve, reject) => {
    pendentes.set(id, {
      resolve: (payload) => {
        if (payload.kind !== kind) {
          reject({
            code: 'protocol',
            title: 'Resposta inesperada',
            reason: `esperava "${kind}", veio "${payload.kind}"`,
            actions: ['logs'],
          } satisfies UiError);
          return;
        }
        resolve(payload as Extract<ResultPayload, { kind: K }>);
      },
      reject,
    });
    api.postMessage({ ...msg, id } as WebviewMessage);
  });
}

/** Dispara e esquece — para ações que não devolvem dado. */
export function send(msg: Saida): void {
  void request(msg, 'ack').catch(() => {
    /* ack perdido não muda nada na tela */
  });
}

export function isUiError(e: unknown): e is UiError {
  return Boolean(e) && typeof e === 'object' && 'code' in (e as object) && 'title' in (e as object);
}

export function toUiError(e: unknown): UiError {
  if (isUiError(e)) return e;
  return {
    code: 'internal',
    title: 'Algo deu errado',
    reason: e instanceof Error ? e.message : 'Sem detalhe disponível.',
    actions: ['retry', 'logs'],
  };
}

/** Estado leve que sobrevive ao recarregamento da webview. */
export function persist(state: Record<string, unknown>): void {
  const atual = (api.getState() as Record<string, unknown>) ?? {};
  api.setState({ ...atual, ...state });
}

export function restore<T>(chave: string, padrao: T): T {
  const atual = (api.getState() as Record<string, unknown>) ?? {};
  return (atual[chave] as T) ?? padrao;
}
