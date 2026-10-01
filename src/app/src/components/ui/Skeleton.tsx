import type { CSSProperties, ReactNode } from 'react'

/** Um bloco de espera. Decorativo (`aria-hidden`): quem anuncia é o `role="status"` da região (`SkeletonRegion`). */
export function Skeleton({ width, height, className = '' }: { width?: string; height?: string; className?: string }) {
  const style: CSSProperties = { width, height }
  return <span className={`skeleton${className ? ` ${className}` : ''}`} style={style} aria-hidden="true" />
}

/** Linhas de texto de espera; a última é mais curta. */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <span className="skeleton-text" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} width={i === lines - 1 && lines > 1 ? '60%' : '100%'} height="12px" />
      ))}
    </span>
  )
}

/** Cartão de projeto de espera (mesmas proporções do `ProjectCard`). */
export function SkeletonCard() {
  return (
    <div className="card skeleton-card" aria-hidden="true">
      <Skeleton width="55%" height="16px" />
      <Skeleton width="80%" height="12px" />
      <Skeleton width="35%" height="12px" />
      <Skeleton width="100%" height="56px" />
      <Skeleton width="100%" height="32px" />
    </div>
  )
}

/**
 * Região de espera: `aria-busy="true"` com UM só `role="status"` em `sr-only` dizendo o que carrega, e o resto
 * (os blocos) escondido do leitor de tela.
 */
export function SkeletonRegion({ label, className, children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <div className={className} aria-busy="true">
      <span role="status" className="sr-only">
        {label}
      </span>
      {children}
    </div>
  )
}
