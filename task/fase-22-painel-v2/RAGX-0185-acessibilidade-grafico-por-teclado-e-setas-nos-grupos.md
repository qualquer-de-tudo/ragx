# RAGX-0185 — Acessibilidade: gráfico por teclado e setas nos grupos

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0179 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-12) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P7) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

O gráfico de economia só responde ao mouse: o `<svg>` é `role="img"` (`TokenSavings.tsx:76`) e o alvo de cada dia reage só a `onMouseEnter` (`:104`), então quem usa teclado ou leitor de tela só chega aos números pela tabela escondida em "Ver em tabela" (`:207-231`). Os grupos de rádio tinham setas em 1 de 3 lugares (a RAGX-0179 unifica o primitivo). E há alvos de clique abaixo dos 24x24 px do WCAG 2.2 (2.5.8): o `.switch` mede 38x22 (`App.css:1673-1676`). Esta tarefa fecha esses três pontos e deixa uma varredura automática para não voltarem.

## Entregáveis

- [x] `TokenSavings.tsx`, `Chart`: o `<svg>` vira `role="group"` com o mesmo `aria-label`; cada dia vira um `rect` focável (`role="img"`, `aria-label` do tipo "12/09: sem RAGX 12.000, com RAGX 3.000, economia 75%" ou "12/09: sem consultas", reaproveitando `formatNumber`/`formatPercent`/`saved`), com `tabIndex` móvel (só o dia ativo está no Tab). Setas esquerda e direita, Home e End movem o dia ativo; o tooltip (`role="status"`) aparece no foco, igual ao hover.
- [x] Foco visível no dia ativo: `.chart-hit:focus-visible` com contorno ou `stroke` em `var(--accent)` (App.css:2070). Conferir em captura que o Chromium desenha o anel em `rect` SVG; se não desenhar, usar o `stroke`.
- [x] A tabela de "Ver em tabela" **fica** (preservar da auditoria): é a alternativa completa.
- [x] Alvos de 24x24: `.switch` ganha área de clique de pelo menos 24 px de altura (padding ou pseudo-elemento, sem mudar o visual de 38x22); varrer o resto por script (item seguinte) e corrigir o que sair abaixo.
- [x] Varredura de alvos no harness da RAGX-0181 (`scripts/visual-check.mjs`, ou um script equivalente se ela ainda não existir): para `button`, `[role=button|switch|radio|tab]`, `a[href]`, `input`, `select`, mede o retângulo e lista os de menos de 24x24 fora de texto corrido (links em linha são isentos pela norma), em cada tela e em 900 e 1280 px.
- [x] `src/__tests__/a11y.test.tsx` com `axe-core` (devDependency; registrar o tamanho; não entra no bundle): renderiza Projetos, Detalhe (as 4 abas), Atividade e Conexões com bridge simulado e exige 0 violações `serious` e `critical`, com `color-contrast` desligado (o jsdom não calcula; o contraste é da RAGX-0178).
- [x] `scroll-padding-bottom` em `.content`, do tamanho do toast se a RAGX-0180 já existir, para o foco não ficar escondido atrás dele (WCAG 2.4.11); sem toast, só o valor de um respiro (token de espaço da 0178).

## Fora de escopo

- Os primitivos em si (RAGX-0179) e o contraste e os tokens (RAGX-0178).
- Link "pular para o conteúdo", modo de alto contraste do Windows (`forced-colors`) e novos gráficos.
- Reescrever o gráfico em outra biblioteca (o gráfico é SVG próprio de propósito, bundle leve).

## Critérios de aceite

- [x] Só com teclado: Tab chega ao gráfico, setas percorrem os 14 dias, o tooltip acompanha, Shift+Tab sai (teste com `userEvent`/`fireEvent.keyDown`).
- [x] Cada dia tem nome acessível com data, valores e economia; dia sem consulta diz "sem consultas" (teste).
- [x] Todo `role="radiogroup"` do app (Projetos x2, Atividade) responde a seta, Home e End (teste de varredura que renderiza as telas e percorre os grupos).
- [x] O script de alvos devolve 0 elementos abaixo de 24x24 nas telas varridas; o "antes" (com o `.switch` de 22 px) fica registrado em Andamento.
- [x] `axe-core`: 0 violações `serious`/`critical` nas quatro telas. Se a instalação do `axe-core` falhar (sem rede), registre e use a varredura manual de papéis e nomes; não marque o critério.
- [x] Bundle (hoje JS 306.822 B, gzip -9 91.745 B): registrar antes e depois; `axe-core` só em teste.

## Testes

- [x] `src/components/project/__tests__/TokenSavings.test.tsx` (novo): foco, setas, Home/End, `aria-label` por dia, tooltip no foco, `<details>` com a tabela preservada.
- [x] `src/__tests__/a11y.test.tsx` (novo): axe nas telas listadas.
- [x] `src/__tests__/radiogroup-keyboard.test.tsx` (novo): todos os grupos de rádio do app.
- [x] `src/pages/__tests__/ProjectsPage.test.tsx` e `ActivityPage.test.tsx` (existentes): sem mudança de asserts.

## Notas

- Confirmado em `TokenSavings.tsx:59-145` (o componente `Chart`) e `App.css:2070-2072` (`.chart-hit { fill: transparent }`); a tabela alternativa existe e deve ficar.
- Premissa da auditoria que se confirmou **em parte**: "radiogroups sem setas (3 duplicações)": só `ProjectsPage.tsx:32-84` tinha setas; os outros dois ganham do primitivo da RAGX-0179, então aqui entra só a varredura que impede a regressão.
- Um `svg` com `role="img"` esconde os filhos da árvore de acessibilidade; por isso a troca para `role="group"`.
- Preservar: `ConfirmButton` em dois cliques, estado nunca só por cor, `prefers-reduced-motion`, `:focus-visible` (`index.css:101-104`).
- `src/__tests__/no-em-dash.test.ts` vale para todo `aria-label` novo.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Nenhuma regressão visual nas telas afetadas (harness a 450, 900 e 1280 px: 36 medições, 0 problema; captura do gráfico com foco vista)
- [x] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0185)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `Chart` de `TokenSavings.tsx` (`role="group"`; um `rect` `role="img"` por dia com `aria-label` por `dayLabel`, `tabIndex` móvel, `onFocus`/`onBlur`/`onKeyDown` com setas, Home e End; balão pelo foco ou pelo hover; a tabela `<details>` ficou intacta), CSS (`.chart-hit:focus-visible` em `stroke`, porque o `outline` não é confiável em `rect` de SVG; `.link-button` e `.project-card-name` com `min-height: 24px`; `.switch::after` com `inset: -2px 0`; `scroll-padding-bottom` em `.content`), harness (alvos de clique).
- **Antes** (harness da 0181 com a nova checagem de alvos, 900 e 1280 px, 24 medições): **180 ocorrências** abaixo de 24x24 em 3 classes: `button.link-button` (20 px de altura, 108 ocorrências), `button.project-card-name` (21 px, 66) e `button.switch` (22 px, 6). O auditor só citava o `.switch`: os outros dois eram achado novo. **Depois**: **0** em 36 medições (450, 900 e 1280 px).
- Achado do harness: o retângulo do elemento não conta a área de clique de um `::after`, e `elementFromPoint` só enxerga o que está na janela; por isso a checagem sonda para fora do retângulo (até 8 px) depois de trazer o elemento para a vista. O `.switch::after` com `inset: -2px 0` dá 24 px (o `inset` é relativo à borda de padding: 22 mais 1 mais 1).
- axe-core: instalado (`^4.13.0`, 3,1 MB em `node_modules`, só em teste). `a11y.test.tsx`: Projetos (grade e lista), Detalhe (as 4 abas), Atividade e Conexões, 0 violações `serious`/`critical`; um caso de sanidade confirma que a varredura enxerga um erro (`button-name`).
- Testes novos: `TokenSavings.test.tsx` (7), `radiogroup-keyboard.test.tsx` (2: os 3 grupos), `a11y.test.tsx` (8). Mudou 1 asserção antiga (`ProjectPage.test.tsx`: o gráfico agora é `group`, não `img`, como a tarefa pedia). `src/test/setup.ts` ganhou `asyncUtilTimeout: 4000`: com a suíte inteira em paralelo o `findBy*` de 1 s falhou uma vez (`app-shortcuts`, da 0183); 2 execuções seguidas da suíte inteira passaram. Painel: 1293 testes verdes, `lint` e `tsc` limpos.
- Bundle: JS 322.519 → **323.159 B** (gzip 96.859 → 97.089); CSS 41.196 → **41.500 B** (gzip 8.217 → 8.284). `axe-core` não entra no bundle.
- Não feito: conferência com leitor de tela real (só atributos ARIA, axe e testes).
