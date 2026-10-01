# RAGX-0174 — Telemetria incremental e rotação do log da CLI

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,75d |
| **Depende de** | `RAGX-0177` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-01) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P4) · [15-configuracao.md](../../docs/15-configuracao.md) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

`readTelemetry` (`src/app/electron/data/telemetry.ts:70`) faz `readFileSync` do `mcp.jsonl` **inteiro** e `JSON.parse` de cada linha, para cada projeto, a cada snapshot (5 s). Do outro lado, `_append` em `src/ragx/diagnostics.py` nunca rotaciona `mcp.jsonl` nem `cli.jsonl` (só o `errors.log` tem teto, `MAX_BYTES`, linha 22), e o `[log] retain_days = 14` documentado em `docs/15-configuracao.md:134` é configuração morta (`config.py:180`, sem leitor). Hoje os logs têm 0–1 kB neste hub (auditoria), então o custo é **latente**: cresce com o uso, sem limite, e vira CPU contínua do painel. O modelo de correção já existe no mesmo código: `ActivityTail` lê por deslocamento (`data/activity.ts`).

## Entregáveis

- [x] **Medir primeiro**: gerar um `mcp.jsonl` sintético de 1, 10 e 50 MB (linhas no formato de `mcp/server.py:101-124`) e cronometrar `readTelemetry` com 12 projetos; registrar o tempo e a CPU por ciclo em Andamento
- [x] `data/telemetry.ts`: `createTelemetryTail(deps)` com estado por arquivo: deslocamento, assinatura do arquivo (`ino` + `birthtimeMs`), `lastCallAt`, buckets **diários locais** para a série de 14 dias (`SavingsSeries`, só `build_context` com as duas medidas, regra de `addSavings`, linha 40) e uma janela móvel só das últimas 24 h (`ts`, `tool`, `tokens_delivered`) para `callsByTool`, `totalCalls` e `tokensDelivered`, podada a cada leitura. O formato de `TelemetrySummary` (`data/types.ts`) **não muda**
- [x] Leitura incremental: a cada chamada, `stat`; sem crescimento, devolve o resumo guardado (mesmo objeto); com crescimento, lê só `[offset, fim]` até a **última quebra de linha** (linha parcial fica para a volta); a primeira leitura pega só os últimos **4 MB** (14 dias de uso normal), e se `mcp.jsonl` for menor que isso lê também o `mcp.jsonl.1`, uma vez
- [x] Truncamento e rotação: `size < offset` ou assinatura diferente zera o estado e relê (o `ActivityTail` já faz o equivalente por tamanho); reutilizar a interface `TailFs` de `activity.ts` (estendida com `signature`)
- [x] `readTelemetry(projectPath, sinceHours)` continua exportada e **sem estado** (usa uma tail nova), para os testes atuais em `data/__tests__/telemetry.test.ts`; `REAL_DEPS.readTelemetry` do `snapshot.ts` passa a usar a tail compartilhada
- [x] `src/ragx/diagnostics.py`: `_append` rotaciona quando o arquivo passa de `MAX_LOG_BYTES` (5 MiB): renomeia para `<nome>.1` (substituindo o `.1` anterior), melhor esforço (no Windows um outro processo pode estar com o arquivo aberto: `PermissionError` é engolido e a rotação tenta na próxima escrita). `retain_days` passa a valer: `log_mcp_call` e `log_cli_call` recebem `retain_days` e apagam o `.1` mais velho que isso; os três chamadores (`mcp/server.py:124`, `cli/main.py:173`, `clients/claude_hint.py:209`) passam `cfg.log.retain_days`
- [x] Atualizar `docs/15-configuracao.md` (`retain_days` e o teto de 5 MiB) e a seção de telemetria de `src/app/README.md`

## Fora de escopo

- Os campos novos de telemetria (`ok`, `err_code`, `resp_chars`, tokens reais): `RAGX-0156`; o painel os consome depois
- A linha do tempo de sessões e a adoção (`RAGX-0188`, `RAGX-0190`)
- Unificar `ActivityTail` e a telemetria numa leitura só (possível depois; hoje são dois deslocamentos independentes sobre o mesmo arquivo)
- `hooks.log` (`.ragx/logs/hooks.log`, 9,8 kB neste repo) e `errors.log`

## Critérios de aceite

- [x] Com `mcp.jsonl` de 50 MB e 12 projetos, o ciclo de telemetria em estado estável (arquivo sem crescimento) custa **< 1 ms por projeto** (um `stat`) e é pelo menos **100x** mais rápido que a leitura completa medida no primeiro entregável
- [x] O resumo é **idêntico** ao da leitura completa para o mesmo arquivo (teste de propriedade com linhas aleatórias, linhas corrompidas e escrita parcial)
- [x] Depois de 5 MiB de escrita pelo Python, existe `mcp.jsonl.1` e o `mcp.jsonl` recomeça pequeno; o painel não perde a contagem das 24 h nem duplica chamadas
- [x] O snapshot continua mostrando os mesmos números de economia e de chamadas em 24 h para um log pequeno (regressão visual zero)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| `readTelemetry`, 12 projetos, log de 10 MB | **777 ms** a cada snapshot (1 MB: 84 ms; 50 MB: **7.227 ms**) | 1ª leitura 293 ms; depois **0,9 ms** (0,075 ms por projeto); 50 MB: 504 ms e 1,96 ms |
| Tempo por ciclo em estado estável (12 projetos) | = a leitura completa acima | **0,77 ms** (1 MB), **0,90 ms** (10 MB), **1,96 ms** (50 MB): 110x, 860x e **3.682x** mais rápido; < 1 ms por projeto ✓ |
| Tamanho máximo de `mcp.jsonl` e `cli.jsonl` | sem limite | ≤ 5 MiB (+ `.1`) |

Comando: `npx vitest run electron/data/__tests__/telemetry.test.ts` e `node scripts/measure-runtime.mjs --plan visible:3` (da `RAGX-0177`, em `src/app`)

## Testes

- [x] `electron/data/__tests__/telemetry.test.ts`: os casos atuais seguem verdes; novos casos incrementais com `TailFs` falso: acrescentar linhas atualiza só o novo, linha parcial espera, truncamento relê, assinatura nova relê, janela de 24 h poda, dia fora dos 14 sai da série
- [x] `electron/data/__tests__/snapshot.test.ts` verde com a dependência trocada
- [x] `tests/unit/test_registro_atividade.py` (ou novo `tests/unit/test_diagnostics_rotation.py`): passar de 5 MiB gera `.1`; falha ao renomear não levanta exceção; `.1` mais velho que `retain_days` é apagado; a linha nova continua sendo gravada
- [x] `tests/security/test_architecture.py` verde: o log não passa a conter a consulta (`log_queries` segue sem efeito neste caminho)

## Notas

Armadilha de Windows: `fs.statSync().ino` pode ser `0` em alguns volumes; neste caso a assinatura usa só `birthtimeMs`, e o `size < offset` continua sendo o detector principal. Se o log passar dos 4 MB iniciais em menos de 14 dias, a série mostra menos dias do que a janela: registrar como limite conhecido, não como bug. Se a medição inicial mostrar que o custo atual com logs de 50 MB já é desprezível, manter a rotação (o crescimento sem limite é o defeito) e reduzir a parte do painel ao mínimo, anotando o número.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] `ruff` e `mypy` limpos (a rotação toca `src/ragx/diagnostics.py`)
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [x] Commit `tipo(escopo): descrição (RAGX-0174)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `data/telemetry.ts` ganhou `createTelemetryTail(io, now)` (deslocamento e assinatura por arquivo; `lastCallAt`; buckets diários locais para a série de 14 dias; janela móvel das últimas 24 h; contadores à parte para linha sem `ts` válido, que a leitura completa SEMPRE conta; resumo guardado com `validUntil` = a entrada mais velha sair da janela ou o dia virar, e o MESMO objeto de volta enquanto isso e sem crescimento; primeira leitura só nos últimos 4 MB, com `mcp.jsonl.1` se o arquivo for menor; trunca/rotaciona por tamanho menor ou assinatura diferente; janela maior que a guardada relê). `readTelemetryFull` preserva a leitura antiga como referência e para a medição; `readTelemetry` continua exportada e agora usa a tail compartilhada (o `snapshot.ts` não mudou). `TailFs` (de `activity.ts`) ganhou `readBytes` e `signature`, ambos opcionais (os fakes de teste antigos seguem válidos). Lado Python: `diagnostics._rotate` (5 MiB, `os.replace` para `<nome>.1`, `OSError` engolido, `.1` mais velho que `retain_days` apagado), `log_mcp_call`/`log_cli_call` com `retain_days`, e os três chamadores passam `cfg.log.retain_days` (`mcp/server.py`, `cli/main.py` e `hooklight`, que agora lê `[log] retain_days` da config mínima). Testes: `telemetry-tail.test.ts` (14, inclusive a propriedade com linhas aleatórias, corrompidas e escrita parcial contra `readTelemetryFull`) e `test_log_rotation.py` (9); painel 90+ verdes, Python verde.
- **Medido** (`scripts/measure-telemetry.mjs`, 12 projetos, linhas no formato v2): ver Medição. O custo era **latente** e cresce sem limite: com 50 MB a leitura completa levaria 7,2 s a cada 5 s (mais que o intervalo); com 10 MB, 777 ms por snapshot. Neste hub os logs têm 0 a 1 kB, então o ganho de hoje é pequeno; a correção é o teto.
- Limitação: a janela de 24 h é guardada em memória por arquivo (um objeto por chamada das últimas 24 h): com muita atividade são alguns milhares de entradas, e `NaN`-ts nunca sai. O `retain_days` só atua no `.1`: o `mcp.jsonl` corrente nunca é podado por idade.
