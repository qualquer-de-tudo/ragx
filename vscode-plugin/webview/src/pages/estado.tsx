/**
 * O contrato de estados de tela, em um lugar só.
 *
 * Toda página tem `loading`, `ready`, `empty` e `error`. Deixar isso a cargo
 * da disciplina de quem escreve a próxima página é como garantir que uma
 * delas, um dia, mostre a tela em branco (§44). Aqui é estrutural: quem usa
 * `Quadro` não consegue esquecer nenhum dos quatro.
 */

import { useEffect, useState } from 'react';

import type { UiError } from '../../../src/protocol';
import { send, toUiError } from '../bridge';
import { EmptyState, ErrorState, Loading } from '../components';

export type Estado<T> =
  | { fase: 'loading' }
  | { fase: 'ready'; dado: T }
  | { fase: 'error'; erro: UiError };

export function usePedido<T>(
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

export function Quadro<T>({
  estado,
  onRetry,
  vazio,
  vazioTitulo,
  vazioDicas,
  children,
}: {
  estado: Estado<T>;
  onRetry: () => void;
  vazio?: (d: T) => boolean;
  vazioTitulo?: string;
  vazioDicas?: string[];
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
    return (
      <EmptyState
        title={vazioTitulo ?? 'Nada aqui ainda'}
        hints={vazioDicas ?? ['Rode `ragx index .` e sincronize.']}
      />
    );
  }
  return <>{children(estado.dado)}</>;
}
