/** Contraste WCAG 2.x, puro (RAGX-0178): lê `#rgb`, `#rrggbb` e `rgba()`, mistura e calcula a razão. Sem dependência. */
export interface Rgba {
  r: number
  g: number
  b: number
  a: number
}

export function parseColor(input: string): Rgba {
  const s = input.trim().toLowerCase()
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/.exec(s)
  if (hex) {
    const h = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join('') : hex[1]
    return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16), a: 1 }
  }
  const fn = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$/.exec(s)
  if (fn) return { r: +fn[1], g: +fn[2], b: +fn[3], a: fn[4] === undefined ? 1 : +fn[4] }
  throw new Error(`cor não reconhecida: ${input}`)
}

/** `fg` por cima de `bg` (alfa de `fg`); `bg` é opaco. */
export function over(fg: Rgba, bg: Rgba): Rgba {
  return {
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  }
}

/** `color-mix(in srgb, fg pct%, bg)`: o mesmo que `fg` com alfa `pct` por cima de `bg`. */
export function mix(fg: Rgba, bg: Rgba, pct: number): Rgba {
  return over({ ...fg, a: fg.a * (pct / 100) }, bg)
}

function channel(v: number): number {
  const c = v / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

export function luminance(c: Rgba): number {
  return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b)
}

/** Razão de contraste entre duas cores opacas (1 a 21). */
export function ratio(a: Rgba, b: Rgba): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}
