# RAGX-0159 — Dedupe de sessão: chunk já entregue volta como referência

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1,5d |
| **Depende de** | RAGX-0154, RAGX-0157 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #1) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-T5, princípio 2) · [07-context-engine.md](../../docs/07-context-engine.md) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `done` |

## Objetivo

Numa sessão, o agente refaz perguntas parecidas e o `build_context` reenvia os mesmos chunks inteiros; o `dedup` do engine (`context/dedup.py`) só limpa repetição **dentro** de um pack, não **entre** packs. A auditoria cita o dedupe de sessão como a aposta nº 1 por impacto ÷ esforço (7.2 #1), mas **não mediu** a sobreposição entre chamadas: medir primeiro. O cache de prompt lê a 0,1×, mas só o que já está no contexto; reenviar o mesmo trecho é gastar token à toa.

## Entregáveis

- [x] **Medir primeiro:** cenário fixo de 3 consultas sobrepostas sobre o próprio repo (ex.: "como o embedder é cacheado", "build_embedder cache por processo", "cache do embedder e dimensão"), `tokens=3000`, com `scripts/medir_fio.py` (0154). Registrar tokens entregues por chamada e quantos `chunk_id` se repetem.
- [x] `src/ragx/context/session.py` (novo): `SessionLedger`, em memória, um por processo (o servidor MCP sobe um por sessão). Guarda só `chunk_id`, caminho, linhas, tokens e quando foi entregue, **nunca o conteúdo**. Limite de entradas e TTL configuráveis; relógio injetável; `threading.Lock`.
- [x] `context/engine.py`: `apply_session(pack, ledger) -> ContextPack`, pós-processamento **depois** do cache (o cache guarda o pack completo; o dedupe é da sessão). Fragmento já entregue vira `ContextReference` em `pack.references`; os novos são marcados. `ContextFragment.chunk_id` vem da 0154.
- [x] `context/render.py`: o markdown ganha, no fim, uma linha "Já entregues nesta sessão (reabra com `get_chunk`): `caminho:linhas [id]`, ...". O custo entra em `estimated_tokens` (a contagem da 0154 vê o texto que sai).
- [x] `src/ragx/config.py` `ContextCfg` (96-102): `session_dedupe: bool = True`, `session_ttl_minutes: int = 45`, `session_max_chunks: int = 2000` (valores iniciais; ajustar pela medição).
- [x] `mcp/server.py`: `KnowledgeAPI.__init__` (155-161) guarda o ledger (só a referência ao objeto); `build_context` (421-453) chama `apply_session`; `get_chunk` (316-342) marca como entregue e **sempre** devolve o conteúdo inteiro, nunca referência. A lógica fica em `ragx.context`, não no servidor.
- [x] Telemetria: `dedupe_refs` e `dedupe_saved_tokens` na linha do log (campos da 0156).
- [x] `get_playbook`/`instructions`: uma frase "chunk já entregue: use `get_chunk(id)`". `docs/07-context-engine.md` (seção "Dedupe de sessão", com as limitações abaixo) e `docs/09-mcp.md`. CHANGELOG.

## Fora de escopo

- **Reaproveitar o orçamento liberado** (segunda passada que preenche o espaço com chunks novos): v1 só encurta a resposta. Anotar como evolução se a medição mostrar espaço.
- Zerar o ledger depois de compactação do contexto ou `/clear`: precisa de um sinal do hook de SessionStart (`source`) que o servidor não tem; é a principal limitação conhecida.
- Persistir o ledger entre processos. Dedupe entre o agente principal e subagentes (o servidor não distingue quem chamou). Dedupe na CLI (`ragx context` não é sessão).
- Dedupe dentro de um pack (já existe, `dedup.py`) e "diff" de chunk editado.

## Critérios de aceite

- [x] Duas consultas com chunks em comum: a segunda traz esses chunks como referência e entrega **menos** tokens que sem o dedupe (teste determinístico com a fixture de `test_context.py`).
- [x] `get_chunk` de qualquer `id` listado como referência devolve o conteúdo íntegro.
- [x] Chunk editado entre as chamadas (id novo, pois o id deriva do conteúdo) volta como conteúdo, não como referência.
- [x] Passado o TTL, o chunk volta como conteúdo. Com `session_dedupe = false`, o markdown é idêntico ao de antes da tarefa.
- [x] A referência não carrega conteúdo; `tests/security` verde com o ledger "aquecido".

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Tokens entregues, cenário de 3 consultas sobrepostas (`tokens=3000`, este repo) | 8.110 (2.747 + 2.608 + 2.755) | **7.767** (2.747 + 2.608 + 2.412), −4,2% |
| Chunks repetidos entre as 3 chamadas | 3 (todos na 3ª; 0 na 2ª) | 3 viram referência |
| Tokens economizados (`dedupe_saved_tokens`) | 0 | 343 |

## Testes

- [x] `tests/unit/test_session_ledger.py` (novo): `mark`/`seen`, TTL com relógio falso, despejo ao passar do limite, acesso concorrente.
- [x] `tests/integration/test_context.py`: duas chamadas seguidas (`proj`), a segunda com `references` e menos tokens; chunk reindexado não vira referência.
- [x] `tests/integration/test_mcp.py`: `KnowledgeAPI.build_context` duas vezes; `get_chunk` do id referenciado devolve tudo; `session_dedupe=False` não altera a resposta.
- [x] `tests/security/test_surfaces.py::test_superficie_mcp_referencias` (novo): com o ledger preenchido, nenhuma resposta contém o segredo da fixture.
- [x] Teste arquitetural "MCP é casca fina" (`tests/security/test_architecture.py`): o ledger vive em `ragx.context`; `ragx.mcp` só segura a referência.

## Notas

- Subagentes compartilham o servidor MCP do pai, mas **não** o contexto dele: um chunk entregue ao pai chegaria ao subagente como referência a algo que ele nunca viu. Mitigação do v1: a referência é recuperável (`get_chunk`) e o TTL é curto. Registrar o risco no CHANGELOG; é um dos itens que o A/B (0162) deve observar.
- Compactação do contexto apaga o que foi entregue, mas o ledger não sabe: mesma mitigação.
- Se a medição mostrar ganho próximo de zero no cenário, registrar em Andamento e deixar `session_dedupe` desligado por padrão em vez de mantê-lo ligado por convicção.
- Confirmado: `context/engine.py:117-129` só dedupe dentro do pack; `server.py:155-161` cria um `KnowledgeAPI` por `build_server`.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0159)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `context/session.py` (`SessionLedger` com TTL, despejo LRU, `threading.Lock` e relógio injetável; `from_config`), `ContextReference` e `ContextPack.references`, `apply_session` em `engine.py` (pós-cache, não altera o pack recebido, só aplica se as referências custarem MENOS que o conteúdo), `format.references_line` e o markdown com a linha "Já entregues nesta sessão", `[context] session_dedupe/session_ttl_minutes/session_max_chunks`, `KnowledgeAPI.ledger` (só a referência; a lógica fica em `ragx.context`), `get_chunk` marca como entregue e SEMPRE devolve o conteúdo, `dedupe_refs`/`dedupe_saved_tokens` na resposta (e `references` no formato `json`) e na telemetria, uma frase nas `instructions`. Testes: `tests/unit/test_session_ledger.py` (9) e `tests/integration/test_session_dedupe.py` (11, inclusive o segredo com o ledger aquecido).
- **Decisão que diverge da task: `session_dedupe` vem DESLIGADO por padrão.** A nota da task manda desligar se o ganho do cenário for próximo de zero em vez de manter "por convicção". Medido: **−4,2%** (343 de 8.110 tokens) num cenário escolhido justamente por ser sobreposto, e só 3 chunks se repetem em 3 chamadas. O risco (cliente que compacta o contexto ou usa `/clear`; subagente que compartilha o servidor mas não o contexto) não se paga com isso. Ligar: `[context] session_dedupe = true`. A RAGX-0162 (A/B) é quem deve decidir; o item "ligado por padrão" do entregável não foi cumprido de propósito.
- Os testes de `test_mcp.py` que reaproveitam um `KnowledgeAPI` entre chamadas ganharam `session_dedupe = false` explícito na fixture (hoje redundante, protege caso o padrão mude).
- Não feito (fora de escopo da v1): reaproveitar o orçamento liberado; zerar o ledger depois de compactação (precisaria do `source` do `SessionStart`).
