# RAGX-0185 — Acessibilidade: gráfico por teclado e setas nos grupos

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0179 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-12) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P7) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

O gráfico de economia só responde ao mouse: o `<svg>` é `role="img"` (`TokenSavings.tsx:76`) e o alvo de cada dia reage só a `onMouseEnter` (`:104`), então quem usa teclado ou leitor de tela só chega aos números pela tabela escondida em "Ver em tabela" (`:207-231`). Os grupos de rádio tinham setas em 1 de 3 lugares (a RAGX-0179 unifica o primitivo). E há alvos de clique abaixo dos 24x24 px do WCAG 2.2 (2.5.8): o `.switch` mede 38x22 (`App.css:1673-1676`). Esta tarefa fecha esses três pontos e deixa uma varredura automática para não voltarem.

## Entregáveis

- [ ] `TokenSavings.tsx`, `Chart`: o `<svg>` vira `role="group"` com o mesmo `aria-label`; cada dia vira um `rect` focável (`role="img"`, `aria-label` do tipo "12/09: sem RAGX 12.000, com RAGX 3.000, economia 75%" ou "12/09: sem consultas", reaproveitando `formatNumber`/`formatPercent`/`saved`), com `tabIndex` móvel (só o dia ativo está no Tab). Setas esquerda e direita, Home e End movem o dia ativo; o tooltip (`role="status"`) aparece no foco, igual ao hover.
- [ ] Foco visível no dia ativo: `.chart-hit:focus-visible` com contorno ou `stroke` em `var(--accent)` (App.css:2070). Conferir em captura que o Chromium desenha o anel em `rect` SVG; se não desenhar, usar o `stroke`.
- [ ] A tabela de "Ver em tabela" **fica** (preservar da auditoria): é a alternativa completa.
- [ ] Alvos de 24x24: `.switch` ganha área de clique de pelo menos 24 px de altura (padding ou pseudo-elemento, sem mudar o visual de 38x22); varrer o resto por script (item seguinte) e corrigir o que sair abaixo.
- [ ] Varredura de alvos no harness da RAGX-0181 (`scripts/visual-check.mjs`, ou um script equivalente se ela ainda não existir): para `button`, `[role=button|switch|radio|tab]`, `a[href]`, `input`, `select`, mede o retângulo e lista os de menos de 24x24 fora de texto corrido (links em linha são isentos pela norma), em cada tela e em 900 e 1280 px.
- [ ] `src/__tests__/a11y.test.tsx` com `axe-core` (devDependency; registrar o tamanho; não entra no bundle): renderiza Projetos, Detalhe (as 4 abas), Atividade e Conexões com bridge simulado e exige 0 violações `serious` e `critical`, com `color-contrast` desligado (o jsdom não calcula; o contraste é da RAGX-0178).
- [ ] `scroll-padding-bottom` em `.content`, do tamanho do toast se a RAGX-0180 já existir, para o foco não ficar escondido atrás dele (WCAG 2.4.11); sem toast, só o valor de um respiro (token de espaço da 0178).

## Fora de escopo

- Os primitivos em si (RAGX-0179) e o contraste e os tokens (RAGX-0178).
- Link "pular para o conteúdo", modo de alto contraste do Windows (`forced-colors`) e novos gráficos.
- Reescrever o gráfico em outra biblioteca (o gráfico é SVG próprio de propósito, bundle leve).

## Critérios de aceite

- [ ] Só com teclado: Tab chega ao gráfico, setas percorrem os 14 dias, o tooltip acompanha, Shift+Tab sai (teste com `userEvent`/`fireEvent.keyDown`).
- [ ] Cada dia tem nome acessível com data, valores e economia; dia sem consulta diz "sem consultas" (teste).
- [ ] Todo `role="radiogroup"` do app (Projetos x2, Atividade) responde a seta, Home e End (teste de varredura que renderiza as telas e percorre os grupos).
- [ ] O script de alvos devolve 0 elementos abaixo de 24x24 nas telas varridas; o "antes" (com o `.switch` de 22 px) fica registrado em Andamento.
- [ ] `axe-core`: 0 violações `serious`/`critical` nas quatro telas. Se a instalação do `axe-core` falhar (sem rede), registre e use a varredura manual de papéis e nomes; não marque o critério.
- [ ] Bundle (hoje JS 306.822 B, gzip -9 91.745 B): registrar antes e depois; `axe-core` só em teste.

## Testes

- [ ] `src/components/project/__tests__/TokenSavings.test.tsx` (novo): foco, setas, Home/End, `aria-label` por dia, tooltip no foco, `<details>` com a tabela preservada.
- [ ] `src/__tests__/a11y.test.tsx` (novo): axe nas telas listadas.
- [ ] `src/__tests__/radiogroup-keyboard.test.tsx` (novo): todos os grupos de rádio do app.
- [ ] `src/pages/__tests__/ProjectsPage.test.tsx` e `ActivityPage.test.tsx` (existentes): sem mudança de asserts.

## Notas

- Confirmado em `TokenSavings.tsx:59-145` (o componente `Chart`) e `App.css:2070-2072` (`.chart-hit { fill: transparent }`); a tabela alternativa existe e deve ficar.
- Premissa da auditoria que se confirmou **em parte**: "radiogroups sem setas (3 duplicações)": só `ProjectsPage.tsx:32-84` tinha setas; os outros dois ganham do primitivo da RAGX-0179, então aqui entra só a varredura que impede a regressão.
- Um `svg` com `role="img"` esconde os filhos da árvore de acessibilidade; por isso a troca para `role="group"`.
- Preservar: `ConfirmButton` em dois cliques, estado nunca só por cor, `prefers-reduced-motion`, `:focus-visible` (`index.css:101-104`).
- `src/__tests__/no-em-dash.test.ts` vale para todo `aria-label` novo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0185)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
