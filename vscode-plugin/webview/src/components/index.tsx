/**
 * Design system do plugin — pequeno de propósito (§30).
 *
 * Um arquivo com doze componentes vale mais que doze arquivos de vinte linhas:
 * quem for mexer vê tudo que existe de uma vez e para de reinventar o botão.
 * Nenhum deles usa cor literal — a paleta é a do VS Code.
 */

import type { ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';

import type { UiError } from '../../../src/protocol';
import type { SystemState } from '../../../src/rag/types';

// ── Button ──────────────────────────────────────────────────────────────
export function Button({
  children,
  onClick,
  variant = 'secondary',
  disabled,
  title,
  full,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: 'primary' | 'secondary' | 'ghost';
  disabled?: boolean;
  title?: string;
  full?: boolean;
}) {
  const base =
    'inline-flex items-center justify-center gap-1.5 px-3 py-1 text-[0.95em] ' +
    'rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
  const estilos = {
    primary: 'bg-btn text-btn-fg hover:bg-btn-hover',
    secondary: 'bg-btn-sec text-btn-sec-fg hover:bg-btn-hover',
    ghost: 'text-fg hover:bg-hover',
  } as const;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`${base} ${estilos[variant]} ${full ? 'w-full' : ''}`}
    >
      {children}
    </button>
  );
}

// ── Input ───────────────────────────────────────────────────────────────
export function Input({
  value,
  onChange,
  placeholder,
  onEnter,
  autoFocus,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  onEnter?: () => void;
  autoFocus?: boolean;
  label: string;
}) {
  return (
    <input
      type="text"
      aria-label={label}
      value={value}
      autoFocus={autoFocus}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => e.key === 'Enter' && onEnter?.()}
      className="w-full bg-bg-input text-fg-input border border-border-input rounded
                 px-2 py-1 outline-none focus:border-focus placeholder:text-fg-muted"
    />
  );
}

// ── Card ────────────────────────────────────────────────────────────────
export function Card({
  title,
  children,
  action,
}: {
  title?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="border border-border rounded bg-bg/40">
      {title && (
        <header className="flex items-center justify-between px-3 py-1.5 border-b border-border">
          <h2 className="font-semibold text-[0.95em]">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-3">{children}</div>
    </section>
  );
}

// ── Badge ───────────────────────────────────────────────────────────────
export function Badge({
  children,
  tone = 'neutral',
  title,
}: {
  children: ReactNode;
  tone?: 'neutral' | 'ok' | 'warn' | 'err' | 'info';
  title?: string;
}) {
  const tons = {
    neutral: 'bg-badge text-badge-fg',
    ok: 'text-ok border border-current',
    warn: 'text-warn border border-current',
    err: 'text-err border border-current',
    info: 'text-info border border-current',
  } as const;
  return (
    <span
      title={title}
      className={`inline-block px-1.5 py-[1px] rounded text-[0.85em] leading-tight ${tons[tone]}`}
    >
      {children}
    </span>
  );
}

// ── Metric ──────────────────────────────────────────────────────────────
export function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <span className="text-fg-muted">{label}</span>
      <span className="font-mono tabular-nums">{value}</span>
    </div>
  );
}

// ── Bar ─────────────────────────────────────────────────────────────────
export function Bar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className="flex items-center gap-2"
    >
      <div className="flex-1 h-1.5 rounded bg-border overflow-hidden">
        <div className="h-full bg-progress" style={{ width: `${pct}%` }} />
      </div>
      {/* Número ao lado da barra: cor e comprimento sozinhos não informam. */}
      <span className="font-mono text-[0.85em] text-fg-muted w-9 text-right">{pct}%</span>
    </div>
  );
}

// ── Status ──────────────────────────────────────────────────────────────
const ESTADOS: Record<SystemState, { tom: 'ok' | 'warn' | 'err' | 'info'; texto: string }> = {
  ready: { tom: 'ok', texto: 'Connected' },
  indexing: { tom: 'info', texto: 'Indexing' },
  syncing: { tom: 'info', texto: 'Syncing' },
  outdated: { tom: 'warn', texto: 'Outdated' },
  warning: { tom: 'warn', texto: 'Warning' },
  securityBlocked: { tom: 'warn', texto: 'Security Blocked' },
  error: { tom: 'err', texto: 'Error' },
  disconnected: { tom: 'err', texto: 'Disconnected' },
};

export function Status({ state, detail }: { state: SystemState; detail?: string }) {
  const e = ESTADOS[state] ?? ESTADOS.disconnected;
  const cor = {
    ok: 'text-ok', warn: 'text-warn', err: 'text-err', info: 'text-info',
  }[e.tom];
  return (
    <span className="inline-flex items-center gap-1.5" title={detail ?? e.texto}>
      {/* O ponto é decoração; o texto é a informação (§18). */}
      <span aria-hidden className={cor}>
        ●
      </span>
      <span>{e.texto}</span>
    </span>
  );
}

// ── Tabs ────────────────────────────────────────────────────────────────
export function Tabs<T extends string>({
  items,
  active,
  onChange,
  label,
}: {
  items: Array<{ id: T; label: string }>;
  active: T;
  onChange: (id: T) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 border-b border-border">
      {items.map((i) => (
        <button
          key={i.id}
          role="tab"
          type="button"
          aria-selected={active === i.id}
          onClick={() => onChange(i.id)}
          className={`px-2.5 py-1 text-[0.95em] border-b-2 -mb-px transition-colors ${
            active === i.id
              ? 'border-focus text-fg'
              : 'border-transparent text-fg-muted hover:text-fg'
          }`}
        >
          {i.label}
        </button>
      ))}
    </div>
  );
}

// ── Tree ────────────────────────────────────────────────────────────────
export interface TreeNode {
  id: string;
  label: string;
  hint?: string;
  children?: TreeNode[];
}

export function Tree({
  nodes,
  onSelect,
  selectedId,
}: {
  nodes: TreeNode[];
  onSelect?: (node: TreeNode) => void;
  selectedId?: string;
}) {
  return (
    <ul role="tree" className="text-[0.95em]">
      {nodes.map((n) => (
        <TreeItem key={n.id} node={n} onSelect={onSelect} selectedId={selectedId} depth={0} />
      ))}
    </ul>
  );
}

function TreeItem({
  node,
  onSelect,
  selectedId,
  depth,
}: {
  node: TreeNode;
  onSelect?: (n: TreeNode) => void;
  selectedId?: string;
  depth: number;
}) {
  const [aberto, setAberto] = useState(depth === 0);
  const temFilhos = Boolean(node.children?.length);
  const selecionado = selectedId === node.id;

  return (
    <li role="treeitem" aria-expanded={temFilhos ? aberto : undefined}>
      <div
        role="button"
        tabIndex={0}
        onClick={() => (temFilhos ? setAberto(!aberto) : onSelect?.(node))}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            temFilhos ? setAberto(!aberto) : onSelect?.(node);
          }
          if (e.key === 'ArrowRight' && temFilhos) setAberto(true);
          if (e.key === 'ArrowLeft' && temFilhos) setAberto(false);
        }}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
        className={`flex items-center gap-1 py-0.5 pr-2 rounded cursor-pointer
                    hover:bg-hover ${selecionado ? 'bg-active text-active-fg' : ''}`}
      >
        <span aria-hidden className="w-3 text-fg-muted shrink-0">
          {temFilhos ? (aberto ? '▾' : '▸') : ''}
        </span>
        <span className="truncate">{node.label}</span>
        {node.hint && (
          <span className="ml-auto text-fg-muted font-mono text-[0.85em] shrink-0">
            {node.hint}
          </span>
        )}
      </div>
      {temFilhos && aberto && (
        <ul role="group">
          {node.children!.map((c) => (
            <TreeItem
              key={c.id}
              node={c}
              onSelect={onSelect}
              selectedId={selectedId}
              depth={depth + 1}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

// ── estados de tela ─────────────────────────────────────────────────────
export function Loading({ label = 'Carregando…' }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="p-6 text-center text-fg-muted">
      <div className="inline-block w-4 h-4 mb-2 rounded-full border-2 border-border border-t-focus animate-spin" />
      <div>{label}</div>
    </div>
  );
}

export function EmptyState({
  title,
  hints,
  action,
}: {
  title: string;
  hints?: string[];
  action?: ReactNode;
}) {
  return (
    <div className="p-6 text-center">
      <p className="font-semibold mb-2">{title}</p>
      {hints?.length ? (
        <ul className="text-fg-muted text-[0.95em] space-y-0.5 mb-3">
          {hints.map((h) => (
            <li key={h}>• {h}</li>
          ))}
        </ul>
      ) : null}
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  onLogs,
  onSettings,
}: {
  error: UiError;
  onRetry?: () => void;
  onLogs?: () => void;
  onSettings?: () => void;
}) {
  return (
    <div role="alert" className="p-4 border border-border rounded">
      <p className="font-semibold text-err mb-1">{error.title}</p>
      {/* Motivo em linguagem de gente. O stack trace fica no Output (§39). */}
      <p className="text-fg-muted text-[0.95em] mb-3">{error.reason}</p>
      <div className="flex flex-wrap gap-2">
        {error.actions.includes('retry') && onRetry && (
          <Button onClick={onRetry} variant="primary">
            Tentar de novo
          </Button>
        )}
        {error.actions.includes('settings') && onSettings && (
          <Button onClick={onSettings}>Configurações</Button>
        )}
        {error.actions.includes('logs') && onLogs && <Button onClick={onLogs}>Ver logs</Button>}
      </div>
    </div>
  );
}

// ── layout ──────────────────────────────────────────────────────────────
/**
 * Lista e detalhe: lado a lado quando há espaço, empilhados quando não há.
 *
 * Na barra lateral (~300px) duas colunas seriam duas colunas ilegíveis, então
 * o detalhe vai para cima da lista — foi o que a pessoa acabou de escolher, e
 * é o que ela quer ver. Na aba do editor a lista continua visível ao lado, que
 * é o ponto inteiro de abrir em tela cheia: comparar sem perder o contexto.
 */
export function Split({
  amplo,
  principal,
  lado,
  larguraLado = 420,
}: {
  amplo: boolean;
  principal: ReactNode;
  lado?: ReactNode;
  larguraLado?: number;
}) {
  if (!lado) return <>{principal}</>;
  if (!amplo) {
    return (
      <div className="space-y-2">
        {lado}
        {principal}
      </div>
    );
  }
  return (
    <div className="flex gap-3 items-start">
      <div className="flex-1 min-w-0">{principal}</div>
      <aside
        style={{ width: larguraLado }}
        className="shrink-0 sticky top-0 max-h-[calc(100vh-8rem)] overflow-y-auto"
      >
        {lado}
      </aside>
    </div>
  );
}

/** Cartões em colunas quando cabe, em uma coluna quando não cabe. */
export function Grade({ children, min = 280 }: { children: ReactNode; min?: number }) {
  return (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))` }}
    >
      {children}
    </div>
  );
}

/**
 * Trecho de código com número de linha.
 *
 * `whitespace-pre-wrap` e não `overflow-x`: quebrar a linha longa é melhor que
 * esconder o fim dela atrás de uma barra horizontal que ninguém arrasta.
 */
export function Codigo({ texto, inicio }: { texto: string; inicio?: number }) {
  const linhas = texto.split('\n');
  return (
    <pre className="text-[0.9em] font-mono whitespace-pre-wrap break-words leading-snug">
      {linhas.map((l, i) => (
        <div key={i} className="flex gap-2">
          {inicio !== undefined && (
            <span aria-hidden className="text-fg-muted select-none tabular-nums shrink-0 w-10 text-right">
              {inicio + i}
            </span>
          )}
          <span className="min-w-0">{l || ' '}</span>
        </div>
      ))}
    </pre>
  );
}

// ── utilidades ──────────────────────────────────────────────────────────
export function useDebounced<T>(valor: T, ms: number): T {
  const [atrasado, setAtrasado] = useState(valor);
  useEffect(() => {
    const t = setTimeout(() => setAtrasado(valor), ms);
    return () => clearTimeout(t);
  }, [valor, ms]);
  return atrasado;
}

/**
 * Lista virtualizada minimalista.
 *
 * Renderizar 5 mil resultados trava a webview (§32). Isto desenha só a janela
 * visível mais uma margem — 40 linhas de código no lugar de uma dependência.
 */
export function VirtualList<T>({
  items,
  itemHeight,
  height,
  render,
  overscan = 6,
}: {
  items: T[];
  itemHeight: number;
  height: number;
  render: (item: T, index: number) => ReactNode;
  overscan?: number;
}) {
  const [scroll, setScroll] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  const inicio = Math.max(0, Math.floor(scroll / itemHeight) - overscan);
  const visiveis = Math.ceil(height / itemHeight) + overscan * 2;
  const fim = Math.min(items.length, inicio + visiveis);

  return (
    <div
      ref={ref}
      onScroll={(e) => setScroll((e.target as HTMLDivElement).scrollTop)}
      style={{ height, overflowY: 'auto' }}
    >
      <div style={{ height: items.length * itemHeight, position: 'relative' }}>
        <div style={{ position: 'absolute', top: inicio * itemHeight, left: 0, right: 0 }}>
          {items.slice(inicio, fim).map((item, i) => (
            <div key={inicio + i} style={{ height: itemHeight }}>
              {render(item, inicio + i)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function fmt(n: number): string {
  return n.toLocaleString('pt-BR');
}
