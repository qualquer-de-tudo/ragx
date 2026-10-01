import type { Plugin } from 'vite'

/**
 * Content-Security-Policy do renderer em PRODUCAO (RAGX-0194). O painel nao carrega nada de fora: scripts e estilos
 * vem do proprio pacote (`file://`, onde cabecalho HTTP nao vale, entao a politica vai num `<meta>`). O `style-src-attr`
 * existe porque ha largura dinamica em `style={{ ... }}` (barras de progresso e de cobertura).
 */
export const CSP_DIRECTIVES: Record<string, string> = {
  'default-src': "'none'",
  'script-src': "'self'",
  'style-src': "'self'",
  'style-src-attr': "'unsafe-inline'",
  'img-src': "'self' data:",
  'font-src': "'self'",
  'connect-src': "'self'",
  'base-uri': "'none'",
  'form-action': "'none'",
}

export const CSP = Object.entries(CSP_DIRECTIVES)
  .map(([name, value]) => `${name} ${value}`)
  .join('; ')

/** Injeta o `<meta>` de CSP em `dist/index.html`. So no build: em dev o Vite injeta script inline e abre WebSocket para o HMR. */
export function cspPlugin(): Plugin {
  return {
    name: 'ragx-csp',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler: () => [
        { tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: CSP }, injectTo: 'head-prepend' },
      ],
    },
  }
}
