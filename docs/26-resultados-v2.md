# 26 — Resultados da v2

Medição dos 14 SLOs da [spec 25](25-spec-v2.md) (seção 3) repetida com o código final da branch `feat/v2` na RAGX-0195.
Tudo abaixo foi **medido de novo nesta rodada**, com o comando da coluna Método; o que não pôde ser medido está como `n/a`
com o motivo. Nenhum número vem de memória nem da estimativa de uma tarefa.

- **Máquina:** Windows 11 (10.0.26200), Intel i5-13600KF (20 núcleos lógicos), 31,8 GB de RAM, GPU AMD RX 7700 XT; carga de
  fundo variável (no Windows os tempos oscilam 2 a 3 vezes entre rodadas, como a [auditoria 24](24-auditoria-v2.md) já
  admitia).
- **Data:** 2026-10-02. **Commit:** `d087721` (`feat/v2`) mais as correções de documentação desta tarefa.
- **Corpus:** o próprio repositório, ~850 documentos e ~9 mil chunks (a spec fala em ~6,6 mil chunks: o corpus cresceu
  com a v2, e a coluna Medido vale para o tamanho de hoje).

## Tabela S1 a S14

| # | Métrica | Hoje (auditoria) | Meta | Medido | Status | Método |
|---|---|---:|---:|---:|---|---|
| S1 | Tokens no fio de `build_context`, `tokens=3000` | 7.684 | ≤ 3.200 | **2.958** (8.535 chars; o servidor declara 2.675) | atingida | `uv run python scripts/medir_fio.py --tool build_context --arg tokens=3000 --arg query="gate de segurança"` |
| S2 | Custo fixo das ferramentas MCP por sessão | 2.660 | ≤ 600 | padrão (`slim`, 6 ferramentas): **385** (compacta); `full` (33): **2.723** | atingida no padrão | `uv run ragx mcp tools [--profile {full,slim}] --json`, régua `ragx.perf.footprint_tokens` (chars/4, compacta) |
| S3 | `get_dictionary` nível 0 | 8.660 | ≤ 800 | **556** no fio (tiktoken; 518 em chars/4); o nível 1 sai em 1.762 e o 2 (completo, o padrão) em 3.180 | atingida | `uv run python scripts/medir_fio.py --tool get_dictionary --arg level=0` |
| S4 | Indexação sem mudança, repo de ~20 mil arquivos | 7,6–15 s | ≤ 1,5 s | **3,7 s** (projeto sintético de 20.000 arquivos Python, 2ª rodada, 0 mudanças; o relatório tinha 7,69 s, em outra condição de máquina); no repo real (850 documentos): **0,21 s** | não atingida | `uv run python scripts/medir_indice_inicial.py --arquivos 20000 --provider hashing --jobs 4 --segunda-rodada` (projeto sintético, 2ª rodada); no repo real, `uv run ragx index . --json` duas vezes |
| S5 | `refresh` incremental, 1 a 4 arquivos | 26–91 s | ≤ 3 s | **1,77 s** (1 arquivo alterado, `indexed: 1`); 0,46 s sem mudança | atingida | `WriteAPI(load_config(), True).refresh()` no processo (comando da RAGX-0131), com um comentário acrescentado ao `README.md` e revertido depois |
| S6 | Edição não commitada visível na busca | indefinida | ≤ 5 s | **1,38–1,42 s** (5 rodadas) | atingida | `ragx touch` real num projeto sintético de 40 arquivos (`hashing`), sondando a busca por keyword a cada 50 ms até o marcador aparecer |
| S7 | `ragx claude hint` (SessionStart) | 481–659 ms | ≤ 120 ms | **75 ms** (p50 de 12; 72–94) | atingida | `uv run python scripts/medir_hooks.py --n 12` (entrada `ragx.entry`; pela `ragx.cli.main` genérica seguem 429 ms, e o hook não usa essa) |
| S8 | Bloqueio síncrono do `git commit` pelo hook | 539–1.041 ms | ≤ 150 ms | **99 ms** (p50 de 12; 79–124) | atingida | idem (`hook-run post-commit`, parte síncrona) |
| S9 | 1ª `search_hybrid` do processo | 3,0–5,0 s | ≤ 600 ms percebidos | **40 ms** (5 amostras: 40, 41, 33, 45, 31); `initialize` em 933 ms | atingida | `uv run python scripts/medir_mcp_frio.py --espera 5` |
| S10 | `search_hybrid` quente | 104–172 ms | ≤ 60 ms | **22 ms** (mediana de 20; 18–26) | atingida | `search(cfg, q, mode="hybrid", limit=10)` em laço no mesmo processo, depois de uma chamada de aquecimento (mede o serviço, sem o transporte MCP) |
| S11 | Painel: processos filhos por minuto, 12 projetos, visível / minimizada | ≈290 / ≈290 | ≤ 20 / 0 | visível **≈4,1** (docker 2,1; tasklist 0,5; powershell 0,5; ragx 1; `git` **0**); minimizada **0**; oculta **0** | atingida | `node scripts/measure-runtime.mjs --plan visible:2,minimized:2,hidden:1 --label fechamento-0195` em `src/app` (Electron 33.4.11, casca de produção, 12 repositórios `git init` de fixture) |
| S12 | Cache do `build_context` com filtro diferente | serve resultado de outro filtro | 0 acertos incorretos | **0**: o teste de propriedade passa | atingida | `uv run pytest tests/integration/test_context.py -k cache`; o teste é `test_propriedade_cache_nunca_devolve_pack_diferente_do_calculado` |
| S13 | Adoção: sessões em projeto indexado que chamam o RAGX | 8% (3 de 38) | medida e visível no painel | **2 de 2** sessões neste repositório, desde 29/09 (universo pequeno) | atingida (é critério de medição) | contagem independente: o `node -e` da RAGX-0190 sobre `.ragx/logs/cli.jsonl` e `mcp.jsonl`; a tela do painel usa `computeAdoption` |
| S14 | Economia real contra baseline de Grep | desconhecida | medida por A/B e publicada | **inconclusiva em tokens faturáveis**: mediana 27,6 mil (sem RAGX) contra 26,0 mil (com), economia pareada +0,8% [IC95% −1,8% a +15,0%] em 11 pares; **custo −18%** (soma US$ 3,26 → 2,68) e **turnos 6 → 3** (mediana); acerto 83% contra 78%; o agente usou o RAGX em 10 de 18 tarefas | medida, não conclusiva | `RAGX_AB_REAL=1 ragx ab --execute --max-calls 36 --arms without,slim --limit 18 --queries <gold do git> --model sonnet --max-turns 15 --setting-sources project,local --with-hooks` (monorepo TypeScript de 3.480 arquivos, 02/10/2026) |

### Notas por linha

- **S1.** Em 2.958 tokens, 1,4% abaixo do pedido de 3.000 (a meta aceitava até 3.200). A rodada da RAGX-0154 tinha dado 3.004:
  o número varia com o texto dos fragmentos que o índice devolve hoje. A medição é no fio do MCP, no `tiktoken` (cl100k), que
  serve para comparar antes e depois, não é o tokenizador do Claude.
- **S2.** O padrão agora é `slim` (6 ferramentas, RAGX-0157): 385 tokens contra 2.723 do `full`. Quem precisa das 33 ferramentas escolhe `[mcp] profile = "full"` ou `--profile full`. Não é uma redução do `full`: o custo dele só cai se ferramentas saírem dele.
- **S3.** O nível 0 do dicionário (resumo extrativo por módulo, glossário, serviços e o repo map por PageRank) custa 556 tokens no fio; `docs/08-dictionary.md` descreve os níveis. A RAGX-0111 (fase 14) não foi pedida: a meta foi atingida pela RAGX-0166 e pelos níveis do dicionário.
- **S4.** A meta é para ~20 mil arquivos, e nesse tamanho **não foi atingida**: 7,69 s (o primeiro índice do mesmo projeto levou 120,9 s, com `hashing` e 4 workers). Está no limite inferior do que a auditoria mediu (7,6 a 15 s), então a v2 não moveu esse número neste corpus sintético, que não tem as pastas de dependências que a poda da RAGX-0129 evita. No repositório real, de 850 documentos, a mesma rodada leva 0,21 s (203 a 212 ms, três medições), abaixo do 1,0 s que a RAGX-0130 se propôs. Investigado na RAGX-0196: a rodada sem mudança voltou a medir ~3,7 s (a diferença para 7,69 s é de condição de máquina, não de código), e o custo é por arquivo, em Python puro: `stat` (1,3 s), 84 padrões do `pathspec` por arquivo (1,5 s) e objetos `Path` (~1,2 s), ~150 µs por arquivo. Não há atalho seguro: `DirEntry.stat()` pode devolver tamanho defasado de arquivo aberto no Windows (quebra a frescura) e reduzir os padrões do ignore mexe no Security Gate. **S4 continua não atingida**; a tarefa fica em `review` para uma pessoa decidir entre reescrever o caminho quente ou definir a meta por tamanho de repositório.
- **S5.** O primeiro `refresh` de um processo frio paga o modelo (~3 s); o número acima é com o processo já quente, como pede a
  meta da RAGX-0131.
- **S6.** Dos ~1,4 s, 400 ms são o debounce da fila e ~0,5 s a partida do `ragx touch`, que roda em `async` (o agente não espera).
- **S7 e S8.** Os números são pela entrada leve `ragx.entry` (RAGX-0143), a que o hook realmente chama.
- **S9 e S10.** Medidos no processo (sem o transporte MCP); no repositório de hoje a matriz tem ~9 mil vetores.
- **S11.** CPU média do conjunto Electron 0,0 nos três estados; RAM 336 MB de working set (194 MB privada) com a janela visível.
  A seção de dados brutos que o script acrescenta a `src/app/docs/medicao-runtime.md` não foi mantida neste commit.
- **S12.** É critério de correção, não de tempo. O arquivo de teste é `tests/integration/test_context.py`.
- **S13.** A razão de 8% da auditoria vinha de transcripts e não se reproduz com estes logs, curtos (a primeira leitura pega
  só os últimos 512 KB). O que se mede é que a contagem existe, bate com a independente e aparece no painel.

## Reprodução de três linhas (critério de aceite)

| Linha | Antes (tarefa de origem) | Agora | Dentro da variação? |
|---|---|---|---|
| S1, tokens | 3.004 (RAGX-0154) | 2.958 | sim (−1,5%) |
| S7, velocidade | 86 ms (RAGX-0143) | 75 ms | sim |
| S11, painel | ~4 filhos/min visível, 0 oculta (RAGX-0171) | ≈4,1 e 0 | sim |

## Suítes com o código final

| Suíte | Resultado |
|---|---|
| `uv run ruff check .` | limpo |
| `uv run mypy src/ragx/core src/ragx/security` | limpo (12 arquivos) |
| `uv run pytest -m "not slow" -n auto` | 2.107 passaram, 5 ignorados |
| `uv run pytest tests/security` | 158 passaram |
| `src/app`: `npm run check` (lint + `tsc` do renderer + vitest) | verde; vitest com 1.923 testes |
| `src/app`: `npx tsc -p tsconfig.electron.json --noEmit` | limpo |

Só o Windows rodou: Linux e macOS ficam para o CI, que roda os três.

## Fora do que a v2 prometeu

Tarefas que terminam em `review` (precisam de uma pessoa) ou `blocked` (dependem de tarefa que o loop não pega sozinho):

| Tarefa | Status | O que falta |
|---|---|---|
| RAGX-0152 primeiro índice em paralelo | `review` | confirmar no CI de Linux e macOS (processos órfãos, `spawn`); 2.000 arquivos: 13–14 s para 6,3–6,8 s |
| RAGX-0162 harness de A/B | `review` | rodar o A/B real (36 chamadas, gasta cota; decisão de não rodar antes da v1): S14 fica `n/a` |
| RAGX-0169 benchmark de modelos | `review` | adotar (ou não) o `nomic-embed-text`; latência de reranker sem número, porque nenhum reranker está em disco |
| RAGX-0170 índice por worktree | `review` | aceitar que a semente de banco ficou de fora (o cache compartilhado sozinho levou o worktree novo a 5% do índice a frio) |
| RAGX-0196 varredura sem mudança em 20 mil arquivos | `review` | S4 não atingida: sem otimização segura; decidir entre reescrever o caminho quente ou medir a meta por tamanho de repositório |
| RAGX-0195 (esta) | `review` | revisão humana do relatório |

Já decididas e fechadas (`done`) antes da v1: RAGX-0145 (a expansão do grafo fica ligada, com a queda de MRR registrada), RAGX-0151 (grafo
incremental, aceito com 47% de edições que preservam os símbolos), RAGX-0157 (`slim` como padrão), RAGX-0192 (auto-update ligado por padrão), 0166 a 0168
(prefixo de contexto, conjunto-ouro do git, repo map).

Pendências de verificação manual do painel (telas e Electron real em Linux e macOS, notificação do Windows) estão nas seções
Andamento das tarefas 0183 a 0194.

## O que mudou além dos SLOs

Resultados que não são um SLO mas saíram da v2, todos com número antes e depois no `CHANGELOG.md`: primeiro índice
2,1 vezes mais rápido (RAGX-0152); cache de embedding em SQLite e em lote, 3,8 s para 0,37 s (0146); watcher com ciclo ocioso
97 ms contra 282 ms (0147); `knowledge/` sem arquivos sujos num `sync` sem mudança (0148); worktree novo em 7,4 s contra
127 s (0170). Correções achadas no caminho: a fila de toque perdia edições quando a leitura do arquivo falhava (0153) e a trava
de indexação ficava presa com PID reutilizado (0153).

### S14: o que o A/B real mostrou (02/10/2026)

Rodado num monorepo TypeScript de terceiros de 3.480 arquivos (do próprio usuário), com 18 tarefas geradas do histórico do git (mensagem do commit como pergunta, arquivos alterados como gabarito), 2 braços (sem RAGX e `slim`), 1 repetição, Sonnet, no máximo 15 turnos: 36 chamadas a `claude -p`. A ordem dos braços girava por tarefa; o braço sem RAGX não recebia nenhum hook do RAGX.

| | Sem RAGX | Com RAGX (`slim`) |
|---|---:|---:|
| Tokens faturáveis, mediana por tarefa | 27.569 | 26.040 |
| Tokens brutos (com `cache_read`), mediana | 264.142 | 180.914 |
| Custo, mediana por tarefa | US$ 0,164 | US$ 0,133 |
| Custo, soma das 18 tarefas | US$ 3,26 | US$ 2,68 (−18%) |
| Turnos, mediana | 6 | 3 |
| Acerto do arquivo certo | 15 de 18 (83%) | 14 de 18 (78%) |
| Tarefas em que usou o RAGX | 0 | 10 de 18 (1 chamada cada, ~900 tokens por resposta) |

**Leitura honesta.** A economia em tokens faturáveis **não se sustenta estatisticamente** (intervalo cruza zero, 11 pares em que os dois acharam o arquivo). Duas razões visíveis nos dados: (1) quase todo o custo faturável é um piso fixo de ~26 mil tokens (`cache_creation`: o prompt do próprio projeto e as ferramentas), que o RAGX não toca; (2) as perguntas eram de "onde está X", que um `Grep` num monorepo bem nomeado já resolve em 3 a 6 turnos. Onde o `Grep` sofreu (12 e 13 turnos), o RAGX respondeu em 2 e 3: 60,8 mil → 4,5 mil, 35,2 mil → 25,9 mil e 30,6 mil → 26,0 mil são as maiores quedas. O ganho que aparece de forma consistente é **menos turnos e menos custo**, não tokens faturáveis. O acerto foi um pouco menor com o RAGX (14 contra 15), diferença que 18 tarefas não distinguem do acaso.

**Limites.** Um projeto, 18 tarefas, 1 repetição, um modelo; tarefas fáceis. Não mede tarefas de entendimento amplo (onde o contexto montado deveria pesar mais). Uma chamada do braço com RAGX teve uma negação de permissão (o relatório ainda não guarda o nome da ferramenta; as chamadas do RAGX estavam liberadas, e essa tarefa usou o RAGX). Antes desta rodada, o harness negava toda chamada ao RAGX (corrigido; ver CHANGELOG); as chamadas de fumaça e de diagnóstico custaram ~US$ 0,7.
