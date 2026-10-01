# RAGX-0186 — Economia em moeda configurável

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,75d |
| **Depende de** | RAGX-0156 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (lacunas de produto) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

O painel mostra economia só em tokens e percentual: "12 mil tokens economizados". O dono quer saber quanto isso vale em R$ ou US$, e é uma lacuna de produto listada na auditoria. O número vem de `telemetry.savings` (`baseline` e `delivered`, `electron/data/types.ts:40-46`), já somado em 14 dias por projeto. Esta tarefa converte essa economia em dinheiro com um **preço que a pessoa informa**: o RAGX não embute tabela de preços, não busca câmbio e não usa rede.

## Entregáveis

- [ ] `PanelSettings.pricing?: { currency: 'BRL' | 'USD' | 'EUR'; perMTokInput: number }` em `electron/settings.ts`, gravado por `updateSettings`. Atenção: `readSettings` monta o objeto campo a campo (linhas 30-38) e **descartaria** um campo novo; estender a leitura com validação (moeda do conjunto, preço finito, `0 < preço ≤ 10000`; qualquer outra coisa vira ausente). Ausente por padrão, e `readSettings` sem o campo continua devolvendo exatamente `{ onboardingDone: false }`.
- [ ] `RendererSettings` ganha `pricing` (único campo de preferência que o renderer vê) e `getSettings` o devolve (`electron/ipc.ts:419-421`).
- [ ] Canal `ragx:setPricing` (`electron/main.ts`, ao lado de `ragx:setOnboardingDone`), `setPricing` em `electron/preload.ts`, em `RagxBridge` e em `createHandlers` (`ipc.ts`): recusa objeto com chave fora de `currency` e `perMTokInput` (mesmo padrão de `JOB_REQUEST_KEYS`), moeda fora do conjunto, preço não finito ou fora de faixa; aceita `null` para limpar. Não é tarefa da fila nem abre processo.
- [ ] `src/money.ts` (puro): `savedMoney(savedTokens, perMTok)` = `max(0, baseline - delivered) / 1_000_000 * perMTok`, e `formatMoney(valor, moeda)` com `Intl.NumberFormat('pt-BR', { style: 'currency', currency })`; valor entre 0 e 0,005 mostra "menos de R$ 0,01" (na moeda escolhida).
- [ ] `src/hooks/usePricing.ts`: lê de `getSettings`, guarda em módulo, grava por `setPricing`; falha de gravação aparece (toast da RAGX-0180 se existir; senão aviso em linha).
- [ ] `TokenSavings.tsx` (cabeçalho do card): par "Economia em dinheiro" com o valor e o selo "estimativa", e "Configurar preço" abrindo um `Modal` (RAGX-0179) com `Segmented` de moeda e o campo "Preço por 1 milhão de tokens de entrada". Sem preço: "Informe quanto você paga por milhão de tokens de entrada para ver a economia em dinheiro."
- [ ] O mesmo valor no resumo de `ProjectsPage` (`Stat` "Tokens economizados", `ProjectsPage.tsx` ~190) e em `ActivityPage` (`Stat` de economia), só quando há preço; nota "estimativa" em ambos.
- [ ] `src/app/README.md`: descrever o preço, onde fica (`settings.json` do painel) e a fórmula.

## Fora de escopo

- Câmbio automático, preço por modelo, preço de saída e de cache, histórico de preços, custo de infraestrutura.
- Baseline honesto contra Grep (RAGX-0163) e telemetria nova (RAGX-0156): esta tarefa usa a série que existir.
- Qualquer valor padrão de preço: não há número oficial embutido.

## Critérios de aceite

- [ ] `savedMoney(2_000_000, 3)` = 6 e `savedMoney` com `delivered > baseline` = 0 (testes de unidade, com entradas explícitas); `formatMoney(6, 'BRL')` sai no formato `pt-BR` da moeda.
- [ ] Sem `pricing`, nenhuma tela mostra valor em dinheiro, só o convite para configurar; nada de "R$ 0,00".
- [ ] Persistência: `updateSettings(dir, { pricing })` sobrevive a reabrir e não apaga `onboardingDone` nem `ollamaMode`; `settings.json` antigo (sem o campo) abre igual a hoje.
- [ ] `setPricing` recusa: chave extra, moeda `'XYZ'`, preço `NaN`, `Infinity`, `-1`, `0`, `10001` e texto; em todos os casos o arquivo não muda (`ipc.test.ts`).
- [ ] Dado ausente degrada: série sem `baseline` (nenhuma chamada com as duas medidas) não mostra valor; o campo de tokens reais da RAGX-0156, se ainda não existir, não quebra a tela.
- [ ] A legenda diz o que o valor **é**: estimativa, só preço de entrada, baseline estimado (a legenda atual de `TokenSavings.tsx:232-234`), sem considerar leitura de cache de prompt, que custa menos.
- [ ] Nenhuma requisição de rede nova (o renderer não ganha `fetch`).
- [ ] Bundle (hoje JS 306.822 B, gzip -9 91.745 B): registrar antes e depois.

## Testes

- [ ] `src/__tests__/money.test.ts` (novo): fórmula, clamp em zero, arredondamento, moedas, "menos de".
- [ ] `electron/__tests__/settings.test.ts` (existente): `pricing` válido, inválido vira ausente, preservação dos outros campos, arquivo antigo.
- [ ] `electron/__tests__/ipc.test.ts` e `preload.test.ts` (existentes): validação do `setPricing`; `setPricing` e o tipo novo na lista exata de métodos do preload.
- [ ] `src/components/project/__tests__/TokenSavings.test.tsx`, `ProjectsPage.test.tsx` e `ActivityPage.test.tsx`: com e sem preço; atualizar os mocks completos de `RagxBridge` (`src/test/snap.ts`, `App.test.tsx`, `useSnapshot.test.ts`, `useJobsConnections.test.ts`).

## Notas

- Confirmado em `electron/settings.ts:7-9` (`RendererSettings` é só `onboardingDone` hoje) e `ipc.ts:419-421`; a regra de IPC não é afetada: o canal leva enum e número, nunca caminho nem argumento de processo.
- O baseline é estimado (~4 caracteres por token) e o valor herda a incerteza; por isso "estimativa" sempre à vista. Se a RAGX-0163 mudar a definição do baseline, a legenda do card muda junto; não recalcule aqui.
- Sem preço padrão por escolha: qualquer número embutido envelheceria e viraria afirmação falsa (a mesma lição do projeto sobre documentação desatualizada).
- `Modal`, `Segmented` e o toast vêm das RAGX-0179 e 0180, que o roteiro põe antes (Bloco 6) mas que **não** são dependência formal: se uma estiver `blocked`, use `<select>` no lugar do `Segmented`, mostre o erro em linha e anote em Andamento.
- `src/__tests__/no-em-dash.test.ts` vale para o texto novo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0186)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
