# RAGX-0179 — Primitivos de UI compartilhados

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0178 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-12, lacunas do design system) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P7) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

O painel não tem biblioteca de UI e os mesmos padrões estão copiados à mão: o controle segmentado em 3 lugares, o interruptor (`role="switch"`) em 3, um `Modal` com foco preso que mora privado dentro de `AddProjectDialog.tsx`, `<svg>` inline em 9 arquivos, 10 atributos `title=` que levam informação que teclado e toque não alcançam e telas vazias escritas à mão. Esta tarefa extrai cada um para `src/components/ui/`, migra os usos existentes e não adiciona dependência.

## Entregáveis

- [x] `ui/Segmented.tsx`, genérico (`Segmented<T extends string>({ label, value, options, onChange })`), extraído de `SegmentedFilter` (`ProjectsPage.tsx:32-84`, o único que já tem setas, Home/End e `tabIndex` móvel). Migrar os 3 usos: `ProjectsPage.tsx:56` (Filtrar), `ProjectsPage.tsx:210-224` (Visualização) e `ActivityPage.tsx:129-142` (Tipo de atividade). Mantém `.segmented`/`.segmented-item` (App.css:1017-1049).
- [x] `ui/Switch.tsx` (`checked`, `onChange`, nome acessível por `label` ou `labelledBy`, `disabled`): migrar `ProjectPage.tsx:218-228` (Hooks de git) e `ClaudeProfiles.tsx:58-69`. O `TopBar.tsx:75-99` é um botão composto com o trilho `.switch-track`: reaproveita só o trilho (`SwitchTrack`), sem mudar o layout.
- [x] `ui/Modal.tsx`, extraído de `AddProjectDialog.tsx:21-102` (foco preso, Esc, clique fora, devolve o foco a quem abriu, `data-autofocus`). `AddProjectDialog` passa a usá-lo; `AddProjectDialog.test.tsx` fica verde sem mudar asserts.
- [x] `ui/IconButton.tsx` com `label` obrigatório no tipo (vira `aria-label`): migrar o `BackButton` (`ProjectPage.tsx:83-102`) e o "Fechar" do modal.
- [x] `ui/Icon.tsx` (`<Icon name size />`, mapa `ICONS` em TSX, sempre `aria-hidden` e `focusable="false"`; sem sprite externo, porque a CSP da RAGX-0194 e o `file://` pedem tudo no bundle). Migrar os `<svg>` de `ConnectionCard`, `AddProjectDialog`, `ProjectCard` (`BranchIcon`), `QueueIndicator`, `Sidebar` (4 ícones, hoje num `Icon` local), `TopBar` e `ProjectPage`. Ficam de fora o `RagxMark` e o gráfico de `TokenSavings`.
- [x] `ui/EmptyState.tsx` (`title?`, `children`, `action?`, `role="status"`, classe `.empty` de App.css:538): migrar "Nenhum projeto neste filtro" (`ProjectsPage.tsx`), `activity-empty` (`ActivityPage.tsx:157`), "Nenhuma indexação registrada ainda" (`Timeline.tsx:95`) e o vazio de `TokenSavings.tsx:238`.
- [x] `ui/Tooltip.tsx`: abre em hover (com atraso) e em foco, liga por `aria-describedby`, Esc fecha, posição por CSS, sem biblioteca. Migrar os `title=` que levam informação única: `ClaudeProfiles.tsx:45`, `ConnectionCard.tsx:242`, `ProjectBits.tsx:65`, `Timeline.tsx:107`, `SecurityPanel.tsx:114`, `TopBar.tsx:83` e `:102`, `ActivityPage.tsx:169`, `ProjectPage.tsx:312`. O `<abbr title>` de `ProjectsPage.tsx:241` fica.
- [x] `ui/index.ts` reexporta os primitivos; um commit por primitivo.

## Fora de escopo

- `Toast` e a falha de ação visível (RAGX-0180); `Skeleton` e primeira pintura (RAGX-0182); paleta Ctrl+K (RAGX-0183).
- Gráfico por teclado, varredura de todos os grupos e alvos de 24 px (RAGX-0185).
- Valores de cor, espaço e fonte (RAGX-0178); breakpoints (RAGX-0181).
- Biblioteca externa de componentes ou de ícones (decidido na spec 25, seção 5.4).

## Critérios de aceite

- [x] Depois da migração, `role="radio"`, `role="switch"` e `<svg` só aparecem dentro de `src/components/ui/` (mais `RagxMark` e o gráfico), garantido por teste de varredura.
- [x] Os 3 grupos segmentados respondem a seta, Home e End, e só o item marcado está na ordem do Tab (hoje 2 dos 3 não). (`primitives.test.tsx`; os três usam o mesmo `Segmented`.)
- [x] `IconButton` sem `label` não compila (`tsc`).
- [x] `package.json` sem dependência nova (`dependencies` idêntico).
- [x] Bundle (hoje JS 306.822 B, gzip -9 91.745 B; CSS 34.835 B, gzip -9 7.096 B em `dist/assets`): registrar antes e depois.
- [ ] Captura a 1280 px de Projetos, Atividade, Conexões e Detalhe antes e depois: igual, exceto o foco visível do tooltip. (NÃO verificado visualmente: sem captura nesta sessão.)

## Testes

- [x] `src/components/ui/__tests__/primitives.test.tsx` (novo): `Segmented` (setas, Home, End, `tabIndex` móvel, `aria-checked`), `Switch` (clique, Espaço, Enter, `disabled`), `Modal` (foco preso, Esc, clique fora, foco devolvido), `Icon` (`aria-hidden`), `EmptyState` (`role="status"`), `Tooltip` (abre no foco, `aria-describedby`, Esc).
- [x] `src/__tests__/ui-primitives.test.ts` (novo): a varredura de `role="radio"`, `role="switch"` e `<svg` fora de `ui/`.
- [x] `ProjectsPage.test.tsx`, `ActivityPage.test.tsx`, `ProjectPage.test.tsx`, `AddProjectDialog.test.tsx` e `ClaudeProfiles.test.tsx` (existentes) verdes; só trocar o que depender de `title=`.

## Notas

- Confirmado: o `.switch` (App.css:1673, 38x22) e o `.switch-track` (App.css:256, 26x14) são dois visuais do mesmo padrão. A altura de 22 px do `.switch` fica abaixo de 24 px (WCAG 2.5.8): corrigir é da RAGX-0185, não daqui.
- Premissa da auditoria que se confirmou em parte: "radiogroups sem setas (3 duplicações)": a duplicação existe, mas 1 dos 3 já tem setas; o primitivo nasce dele.
- Tooltip em elemento que não é focável (texto truncado, como o caminho em `ClaudeProfiles.tsx:45`) precisa de `tabIndex={0}` no gatilho.
- `npm run lint` usa `react-refresh/only-export-components` (`eslint.config.js`): um `.tsx` que exporta componente e constante reclama; `ICONS` e tipos de opção ficam em `.ts`.
- Sem `<style>` nem `<script>` inline (CSP da RAGX-0194); o atributo `style` é permitido. `no-em-dash.test.ts` vale para todo texto novo.
- Se um uso não couber no primitivo sem distorcê-lo, deixe-o como está e anote em Andamento; não force.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização) (só os testes de renderização; sem screenshot)
- [x] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0179)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Criados em `src/components/ui/`: `Segmented`, `Switch` (+ `SwitchButton` e `SwitchTrack`), `Modal` (movido de `AddProjectDialog`), `IconButton`, `Icon` + `icons.ts`, `EmptyState`, `Tooltip` e `index.ts`. Migrados: os 3 segmentados (Filtrar, Visualização, Tipo de atividade), os 3 interruptores (Hooks de git, perfis do Claude, barra superior), o `Modal`, o `BackButton` e o "Fechar", os `<svg>` de `ConnectionCard`, `ProjectCard`/`ProjectPage` (`BranchIcon`, que saiu), `QueueIndicator`, `Sidebar` (o `Icon` local saiu) e `TopBar`, os 4 vazios (`ProjectsPage`, `ActivityPage`, `Timeline`, `TokenSavings`) e os `title=` de `ClaudeProfiles`, `ConnectionCard`, `ProjectBits`, `Timeline`, `SecurityPanel`, `TopBar` (os dois), `ActivityPage` e `ProjectPage` (barras por ferramenta). O `<abbr title>` ficou, como previsto.
- Decisões fora do roteiro: (1) `SwitchButton` em `ui/Switch.tsx` para o botão composto da barra superior, porque a varredura exige `role="switch"` só em `ui/` e o `SwitchTrack` sozinho deixaria o `role` no `TopBar`. (2) `Tooltip` sem wrapper (render prop `{(tip) => <el {...tip}>}`) e com o balão em portal com `position: fixed`: um wrapper quebraria o HTML de `dl`, `ul` e `ol`, e um balão absoluto seria cortado pelo `overflow: hidden` dos textos truncados, que são justamente onde havia `title`. (3) Sem refs no `Tooltip`: o atraso do mouse é um efeito sobre estado (`react-hooks/refs` reclamou da versão com `useRef`).
- Testes: `primitives.test.tsx` (15) e `ui-primitives.test.ts` (varredura). Dois existentes tiveram de mudar por depender do que migrou: `shell.test.tsx` (o `title` do interruptor virou foco + `role=tooltip` + `aria-describedby`) e `ActivityPage.test.tsx` (`getByRole('status')` único: o vazio do feed agora também é `status`). Painel: 1160 testes verdes, `lint` e `tsc` limpos; `package.json` sem dependência nova.
- Bundle: JS 309.626 → **309.723 B** (gzip 92.611 → 93.139); CSS 36.808 → **37.143 B** (gzip 7.446 → 7.490). (Contra o "hoje" da tarefa, 306.822 e 34.835, a diferença vem sobretudo das tarefas 0175 e 0178.)
- Desvio: um commit só para a tarefa (a tarefa pedia um por primitivo); o roteiro do loop manda um por tarefa e o código dos primitivos é interdependente (`Modal` usa `IconButton` usa `Icon`).
- NÃO feito: capturas antes/depois (sem navegador); o balão não foi visto na tela, só testado em jsdom.
