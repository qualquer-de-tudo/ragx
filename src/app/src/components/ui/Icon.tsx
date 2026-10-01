import { ICONS, type IconName, type Shape } from './icons'

/**
 * Ícone em SVG inline (sem sprite externo: a CSP de produção e o `file://` pedem tudo no bundle). Sempre decorativo:
 * `aria-hidden` e `focusable="false"`; quem precisa de nome acessível usa `IconButton` ou texto ao lado.
 */
export function Icon({
  name,
  size = 16,
  strokeWidth = 1.8,
  className,
}: {
  name: IconName
  size?: number
  strokeWidth?: number
  className?: string
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {(ICONS[name] as readonly Shape[]).map((s, i) => {
        if ('path' in s) return <path key={i} d={s.path} />
        if ('rect' in s) {
          const [x, y, width, height, rx] = s.rect
          return <rect key={i} x={x} y={y} width={width} height={height} rx={rx} />
        }
        const [cx, cy, r] = s.circle
        return <circle key={i} cx={cx} cy={cy} r={r} />
      })}
    </svg>
  )
}
