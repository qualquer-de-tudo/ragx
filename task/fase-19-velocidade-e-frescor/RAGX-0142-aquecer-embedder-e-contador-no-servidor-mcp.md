# RAGX-0142 — Aquecer embedder e contador no servidor MCP

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0132 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-06, C-08) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V9, S9) · [05-busca.md](../../docs/05-busca.md) · [09-mcp.md](../../docs/09-mcp.md) · [15-configuracao.md](../../docs/15-configuracao.md) |
| **Status** | `todo` |

## Objetivo

A primeira `search_hybrid` de cada processo custa **3,0–3,3 s** (logs reais 3,0–5,0 s): a construção do `FastEmbedEmbedder` leva 3,98 s (ONNX 1,8 s, tokenizer 0,95 s, imports 1,05 s) e o `tiktoken` mais 0,9 s no primeiro `count_tokens` (M-06, C-08). A pessoa paga isso na primeira pergunta de cada sessão, porque cada sessão sobe um servidor novo. O servidor MCP vive a sessão inteira e fica ocioso depois do `initialize`: dá para carregar tudo em segundo plano nesse intervalo, e a meta é **≤ 600 ms percebidos** na primeira busca (S9).

## Entregáveis

- [ ] **Medir primeiro**: script que sobe `ragx mcp serve` por stdio (cliente do pacote `mcp`), mede `initialize` e a 1ª `search_hybrid` com e sem espera de 5 s entre os dois; registrar em Medição
- [ ] `build_embedder` (`src/ragx/embeddings/__init__.py:44-55`) passa a ser seguro entre threads: trava por chave de cache, de modo que a thread de aquecimento e a 1ª busca esperem a **mesma** construção em vez de construir duas (dois modelos = ~1,4 GB). Hoje `_CACHE` é um `dict` sem trava
- [ ] Mesma garantia para `get_counter`/`count_tokens` (`src/ragx/tokens.py:56-73`, `_default` global criado sem trava)
- [ ] `src/ragx/mcp/warmup.py` (novo): `warm(cfg)` faz `build_embedder(cfg)` + `embed_query("ragx")` + `count_tokens("ragx")` (+ `load_index` quando a RAGX-0134 já o cacheia), cada passo em `try/except` que grava em `.ragx/logs/errors.log` via `ragx.diagnostics.log_exception` e nunca propaga
- [ ] `ragx.mcp.server.serve` (`src/ragx/mcp/server.py:772-780`) dispara `warm` numa thread `daemon` assim que o servidor começa a rodar (ou no `lifespan` do `MCPServer`, aceito em mcp 2.2.0: conferir qual dos dois deixa o `initialize` mais rápido); **só** quando `cfg.db_path.exists()` e `cfg.mcp.warmup` é verdadeiro
- [ ] `McpCfg.warmup: bool = True` em `src/ragx/config.py:136-145`, documentado em `docs/15-configuracao.md` (quem tem 3 servidores abertos e pouca RAM desliga)
- [ ] Servidor registrado globalmente em pasta sem projeto RAGX **não aquece nada** (sem 680 MB de RAM à toa)
- [ ] Atualizar `docs/05-busca.md` e `docs/09-mcp.md` (primeira busca, aquecimento, `[mcp] warmup`)

## Fora de escopo

- Compartilhar um único modelo ONNX entre vários servidores (sobra de M-13: um servidor por sessão continua)
- Tirar `state_dir` da chave do cache e o teto FIFO de 4 instâncias (C-08, parte): o teste `tests/unit/test_embedder_cache.py` protege "raízes diferentes não compartilham"; a RAGX-0153 revê a pasta de modelos
- Fixar o `initialize` em menos de ~1 s (hoje 0,96–1,28 s, imports): aqui só se garante que o aquecimento não o atrasa
- Ollama `localhost` → `127.0.0.1` (RAGX-0132, pré-requisito)

## Critérios de aceite

- [ ] 1ª `search_hybrid` após o `initialize` e 5 s de espera: **≤ 600 ms** (S9)
- [ ] Busca disparada **durante** o aquecimento (sem esperar) devolve resultado correto e constrói o modelo uma vez só (contador de construção = 1)
- [ ] O aquecimento não atrasa o `initialize` em mais de 100 ms sobre a linha de base
- [ ] `[mcp] warmup = false` e pasta sem índice: nenhuma thread, nenhum modelo carregado
- [ ] Falha do embedder (Ollama fora) no aquecimento não derruba o servidor nem muda o `degraded` da busca

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| 1ª `search_hybrid` do processo (S9) | 3,0–3,3 s (logs reais 3,0–5,0 s) | |
| `ragx mcp serve` até `initialize` | 0,96–1,28 s | |
| Construção do `FastEmbedEmbedder` | 3,98 s | |
| Primeiro `count_tokens` (tiktoken) | 0,9 s | |

Comando: `uv run python scripts/medir_mcp_frio.py --espera 5` (criar; deve imprimir `initialize_ms` e `primeira_busca_ms`, mediana de 5 execuções).

## Testes

- [ ] `tests/unit/test_embedder_cache.py`: 8 threads chamando `build_embedder` juntas constroem **uma** instância (espiar o contador de construção); regressão que falha hoje
- [ ] `tests/unit/test_tokens_threads.py`: idem para `count_tokens`
- [ ] `tests/integration/test_mcp_warmup.py`: `build_server` + `serve` simulado com provider `hashing` e `FastEmbedEmbedder` trocado por um falso lento (0,3 s) → a busca logo depois do `initialize` espera o aquecimento e não constrói duas vezes; `warmup=false` não cria thread; sem índice não aquece
- [ ] `tests/integration/test_mcp_warmup.py`: exceção no aquecimento vai para `errors.log` e o servidor continua respondendo
- [ ] `tests/security/test_architecture.py` continua verde: `ragx.mcp.warmup` não importa `os`, `pathlib`, `subprocess` nem rede (o log vai por `ragx.diagnostics`)

## Notas

- Confirmado em `src/ragx/embeddings/__init__.py:21,44-55` (`_CACHE` sem trava; `_chave` inclui `str(cfg.state_dir)`), `src/ragx/tokens.py:66-73` (`_default` lazy) e `src/ragx/mcp/server.py:772-780` (`serve` chama `build_server(...).run(transport="stdio")`).
- O provider padrão em `config.py:59` é `ollama`: construir o `OllamaEmbedder` não custa nada; o que o aquecimento faz aí é a 1ª requisição (abrir conexão e deixar o Ollama carregar o modelo). Os 3,98 s medidos são do `fastembed`, que é o provider deste repo (`ragx.toml`). Medir nos dois.
- `tiktoken` é opcional (`ragx[tokens]`): sem ele o contador é heurístico e o aquecimento desse passo não custa nada.
- Cuidado com o GIL: imports pesados na thread de aquecimento podem atrasar o `initialize`. Se a medição mostrar isso, iniciar a thread depois do 1º `initialize` (via `lifespan`) em vez de em `serve()`.
- Se a 1ª busca continuar acima de 600 ms com o aquecimento concluído, a diferença é `load_index` (C-02): confirmar que a RAGX-0134 está em `done`; registrar em Andamento em vez de improvisar aqui.
- Não aquecer o grafo nem o dicionário: seriam gastos sem uso comprovado.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0142)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
