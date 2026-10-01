/**
 * Breakpoints do painel (RAGX-0181), os únicos permitidos em `@media`. Espelham o comentário do topo de `App.css` e o
 * fim de `index.css`; `css-breakpoints.test.ts` confere que o CSS não usa outro valor.
 *
 * - 640: telefone ou zoom de 300% (barra superior em duas linhas, barra lateral de 56 px)
 * - 900: janela estreita ou zoom de 200% (900 DIP viram 450 px de CSS): barra superior compacta, grades de uma coluna
 * - 1200: tela larga (a largura máxima do conteúdo sobe)
 */
export const BREAKPOINTS = [640, 900, 1200] as const
