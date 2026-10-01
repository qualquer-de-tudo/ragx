# RAGX-0159 — Dedupe de sessão: chunk já entregue volta como referência

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1,5d |
| **Depende de** | RAGX-0154, RAGX-0157 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #1) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-T5, princípio 2) · [07-context-engine.md](../../docs/07-context-engine.md) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `doing` |

## Objetivo

Numa sessão, o agente refaz perguntas parecidas e o `build_context` reenvia os mesmos chunks inteiros; o `dedup` do engine (`context/dedup.py`) só limpa repetição **dentro** de um pack, não **entre** packs. A auditoria cita o dedupe de sessão como a aposta nº 1 por impacto ÷ esforço (7.2 #1), mas **não mediu** a sobreposição entre chamadas: medir primeiro. O cache de prompt lê a 0,1×, mas só o que já está no contexto; reenviar o mesmo trecho é gastar token à toa.

## Entregáveis

- [ ] **Medir primeiro:** cenário fixo de 3 consultas sobrepostas sobre o próprio repo (ex.: "como o embedder é cacheado", "build_embedder cache por processo", "cache do embedder e dimensão"), `tokens=3000`, com `scripts/medir_fio.py` (0154). Registrar tokens entregues por chamada e quantos `chunk_id` se repetem.
- [ ] `src/ragx/context/session.py` (novo): `SessionLedger`, em memória, um por processo (o servidor MCP sobe um por sessão). Guarda só `chunk_id`, caminho, linhas, tokens e quando foi entregue, **nunca o conteúdo**. Limite de entradas e TTL configuráveis; relógio injetável; `threading.Lock`.
- [ ] `context/engine.py`: `apply_session(pack, ledger) -> ContextPack`, pós-processamento **depois** do cache (o cache guarda o pack completo; o dedupe é da sessão). Fragmento já entregue vira `ContextReference` em `pack.references`; os novos são marcados. `ContextFragment.chunk_id` vem da 0154.
- [ ] `context/render.py`: o markdown ganha, no fim, uma linha "Já entregues nesta sessão (reabra com `get_chunk`): `caminho:linhas [id]`, ...". O custo entra em `estimated_tokens` (a contagem da 0154 vê o texto que sai).
- [ ] `src/ragx/config.py` `ContextCfg` (96-102): `session_dedupe: bool = True`, `session_ttl_minutes: int = 45`, `session_max_chunks: int = 2000` (valores iniciais; ajustar pela medição).
- [ ] `mcp/server.py`: `KnowledgeAPI.__init__` (155-161) guarda o ledger (só a referência ao objeto); `build_context` (421-453) chama `apply_session`; `get_chunk` (316-342) marca como entregue e **sempre** devolve o conteúdo inteiro, nunca referência. A lógica fica em `ragx.context`, não no servidor.
- [ ] Telemetria: `dedupe_refs` e `dedupe_saved_tokens` na linha do log (campos da 0156).
- [ ] `get_playbook`/`instructions`: uma frase "chunk já entregue: use `get_chunk(id)`". `docs/07-context-engine.md` (seção "Dedupe de sessão", com as limitações abaixo) e `docs/09-mcp.md`. CHANGELOG.

## Fora de escopo

- **Reaproveitar o orçamento liberado** (segunda passada que preenche o espaço com chunks novos): v1 só encurta a resposta. Anotar como evolução se a medição mostrar espaço.
- Zerar o ledger depois de compactação do contexto ou `/clear`: precisa de um sinal do hook de SessionStart (`source`) que o servidor não tem; é a principal limitação conhecida.
- Persistir o ledger entre processos. Dedupe entre o agente principal e subagentes (o servidor não distingue quem chamou). Dedupe na CLI (`ragx context` não é sessão).
- Dedupe dentro de um pack (já existe, `dedup.py`) e "diff" de chunk editado.

## Critérios de aceite

- [ ] Duas consultas com chunks em comum: a segunda traz esses chunks como referência e entrega **menos** tokens que sem o dedupe (teste determinístico com a fixture de `test_context.py`).
- [ ] `get_chunk` de qualquer `id` listado como referência devolve o conteúdo íntegro.
- [ ] Chunk editado entre as chamadas (id novo, pois o id deriva do conteúdo) volta como conteúdo, não como referência.
- [ ] Passado o TTL, o chunk volta como conteúdo. Com `session_dedupe = false`, o markdown é idêntico ao de antes da tarefa.
- [ ] A referência não carrega conteúdo; `tests/security` verde com o ledger "aquecido".

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Tokens entregues, cenário de 3 consultas sobrepostas | medir primeiro | |
| Chunks repetidos entre as 3 chamadas | medir primeiro | |
| Tokens economizados (`dedupe_saved_tokens`) | 0 | |

## Testes

- [ ] `tests/unit/test_session_ledger.py` (novo): `mark`/`seen`, TTL com relógio falso, despejo ao passar do limite, acesso concorrente.
- [ ] `tests/integration/test_context.py`: duas chamadas seguidas (`proj`), a segunda com `references` e menos tokens; chunk reindexado não vira referência.
- [ ] `tests/integration/test_mcp.py`: `KnowledgeAPI.build_context` duas vezes; `get_chunk` do id referenciado devolve tudo; `session_dedupe=False` não altera a resposta.
- [ ] `tests/security/test_surfaces.py::test_superficie_mcp_referencias` (novo): com o ledger preenchido, nenhuma resposta contém o segredo da fixture.
- [ ] Teste arquitetural "MCP é casca fina" (`tests/security/test_architecture.py`): o ledger vive em `ragx.context`; `ragx.mcp` só segura a referência.

## Notas

- Subagentes compartilham o servidor MCP do pai, mas **não** o contexto dele: um chunk entregue ao pai chegaria ao subagente como referência a algo que ele nunca viu. Mitigação do v1: a referência é recuperável (`get_chunk`) e o TTL é curto. Registrar o risco no CHANGELOG; é um dos itens que o A/B (0162) deve observar.
- Compactação do contexto apaga o que foi entregue, mas o ledger não sabe: mesma mitigação.
- Se a medição mostrar ganho próximo de zero no cenário, registrar em Andamento e deixar `session_dedupe` desligado por padrão em vez de mantê-lo ligado por convicção.
- Confirmado: `context/engine.py:117-129` só dedupe dentro do pack; `server.py:155-161` cria um `KnowledgeAPI` por `build_server`.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0159)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
