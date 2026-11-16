# RAGX-0199 — Saúde do core e coerência entre as telas do painel

| | |
|---|---|
| **Fase** | 23 — Pós-lançamento |
| **Prioridade** | P1 |
| **Estimativa** | 2d |
| **Depende de** | — |
| **Documentação** | [04-indexacao.md](../../docs/04-indexacao.md) · [09-mcp.md](../../docs/09-mcp.md) · [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) |
| **Status** | `review` |

## Objetivo

Corrigir o que o uso real de 27/10 a 16/11 mostrou nos logs de 9 projetos (Juriflux, crm-project e o próprio RAGX):

- No Juriflux foram **2.802 indexações em 13 dias (~4,6 h)**. 534 delas eram varreduras completas (~17.900 arquivos, de 10 a 92 s cada) disparadas por uma edição do agente que chegou com a trava ocupada: o pedido pendente do `touch` virava `_index_once` completo, e o lote voltava à fila para ser reindexado de novo.
- `lock.mark_pending` estourou `PermissionError` no Windows (2 vezes no crm-project), perdendo o pedido e deixando `.tmp` órfão. Lotes `touch.queue.*.claimed` de processos mortos ficavam para sempre, sem ninguém reprocessá-los.
- `status.json` nunca trazia `last_error` (a consulta filtrava `error IS NULL`), então o estado "Com problema" do painel era inalcançável.
- O log do MCP não gravava `degraded` (busca que caiu para palavra-chave com o Ollama fechado aparecia como `ok`) nem o cliente quando não era o Claude Code; `hooks.log` não tinha hora.
- O painel contava o lembrete (`nudge`) como uso do RAGX em Atividade › Sessões, contava eventos `session_start` como sessões, olhava só `~/.claude.json` no card do Claude Code, somava todos os clientes na "última chamada MCP", deixava o cabeçalho vermelho por causa do Ollama mesmo sem projeto que precise dele e mostrava frescor diferente no selo e no "Está em dia?".

## Entregáveis

- [x] Pedido pendente de origem por caminho (`touch`, `mcp:touch`, `paths`) é drenado pela fila de arquivos tocados, sob a trava já tomada, sem varrer o projeto; pedido de hook/CLI continua fazendo a passada incremental, e um pedido de caminho nunca rebaixa um pedido completo
- [x] `mark_pending` tenta de novo no Windows e nunca deixa `.tmp` órfão; `claim` recupera lotes `.claimed` de processo morto
- [x] `status.json` traz `last_error` da última rodada que falhou depois da última que deu certo
- [x] `mcp.jsonl` grava `degraded`; a origem reconhece outros clientes além do Claude Code; `hooks.log` com data e hora
- [x] Atualização do grafo depois de um lote do `touch` roda sob a trava de indexação
- [x] Painel: lembrete não é uso nem "em uso agora"; sessões contadas por id; card do Claude Code olha os perfis e é reconferido ao alternar; "última chamada MCP" por cliente; Ollama só pesa na saúde quando algum projeto o usa; selo e "Está em dia?" com o mesmo critério; janela da adoção rotulada
- [x] Teste de latência do lembrete estável sob `-n auto`
- [x] CHANGELOG em `[Não lançado]`

## Fora de escopo

- RAGX-0198 (perguntar ao git o que mudou na varredura completa): esta tarefa só evita varreduras desnecessárias, não acelera a que é necessária
- Mudar o ID do modelo de embedding do fastembed para incluir a versão da biblioteca (invalidaria todos os vetores existentes; decisão à parte)
- Mudar o comportamento do agente (dica e lembrete) para aumentar a adoção

## Critérios de aceite

- [x] Teste: lote do `touch` que chega com a trava ocupada é indexado pelo dono da trava SEM rodada `incremental`
- [x] `tests/security` verde sem alteração
- [x] `uv run pytest -m "not slow" -n auto` e `npm run check` verdes

## Resultado

- Lote do `touch` com a trava ocupada: o dono a atende com run `paths` (teste `test_lote_do_touch_com_trava_ocupada_nao_vira_varredura_completa`); antes, `incremental` completo.
- Fumaça por stdio com um cliente MCP real: `client` vem do `clientInfo` e `degraded: true` aparece com o Ollama inacessível.
- `uv run pytest -m "not slow" -n auto` e `tests/security` verdes; `npm run check`: 112 arquivos, 2.056 testes.
- Limitação: a lista de projetos e a bandeja ainda não enxergam alteração não commitada (o snapshot não roda `git status`); só a página do projeto usa a regra única de frescor.
