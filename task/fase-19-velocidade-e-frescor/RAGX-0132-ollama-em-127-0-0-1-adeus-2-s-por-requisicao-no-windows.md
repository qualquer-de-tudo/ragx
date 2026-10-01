# RAGX-0132 — Ollama em `127.0.0.1` (adeus 2 s por requisição no Windows)

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,25d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-03) · [25-spec-v2.md](../../docs/25-spec-v2.md) · [15-configuracao.md](../../docs/15-configuracao.md) · [ADR-0004](../../docs/adr/ADR-0004-embeddings.md) |
| **Status** | `done` |

## Objetivo

O endereço padrão do Ollama é `http://localhost:11434` (`config.py:62`, `embeddings/ollama.py:28`). No Windows cada requisição paga ~2 s a mais. Medido: `/api/tags` em 2,05–2,1 s contra 6–12 ms em `127.0.0.1`; `/api/embed` de 1 texto em 2,06 s contra 23–44 ms; por chunk, 87,5 ms (batch 32) a 2.085 ms (batch 1) contra 9,8–12,3 ms. A hipótese (a evidência é o tempo medido): `localhost` resolve para `::1` primeiro, o Ollama escuta só em IPv4, e a conexão espera o tempo de falha antes de cair em `127.0.0.1`.

## Entregáveis

- [x] **Medir primeiro** (só se o Ollama estiver rodando; senão registrar "não medido" e validar só pelos testes): tempo de `GET /api/tags` e de um `POST /api/embed` com `localhost` e com `127.0.0.1`.
- [x] `resolve_base_url(url: str) -> str` em `src/ragx/embeddings/ollama.py`: troca o host `localhost` (qualquer caixa) por `127.0.0.1`, preservando esquema, porta e caminho; acrescenta `http://` se faltar esquema; **não mexe** em outro host (IP, `[::1]`, nome de rede).
- [x] `OllamaEmbedder.__init__` (`ollama.py:36`) aplica `resolve_base_url`; o padrão do parâmetro (linha 28) e `EmbeddingCfg.base_url` (`config.py:62`) passam a `http://127.0.0.1:11434`.
- [x] `OLLAMA_HOST` (`config.py:260-261`) passa pelo mesmo normalizador.
- [x] `_chave` do cache de embedder (`embeddings/__init__.py:28-36`) usa a URL resolvida, para duas grafias da mesma URL não criarem duas instâncias.
- [x] `ragx doctor` (`cli/commands/doctor.py:168,179,196`) usa a URL resolvida nas requisições e na mensagem de erro.
- [x] Documentação: `docs/15-configuracao.md` (linhas 56 e 299) e `docs/GUIA-DE-USO.md` (linha 123) dizem `127.0.0.1` e explicam que `localhost` é convertido.
- [x] CHANGELOG com o número antes/depois.

## Fora de escopo

- O painel Electron também usa `localhost` (`src/app/electron/connections/checks.ts:419,584`): é a RAGX-0173.
- Trocar o modelo de embedding (RAGX-0103) ou ajustar `batch` e GPU.
- Aquecer o modelo no Ollama (`keep_alive`) e o embedder no MCP: RAGX-0142.
- Resolver `0.0.0.0` (valor comum de `OLLAMA_HOST` para escutar em todas as interfaces, que não é um destino de conexão no Windows): anotar como pendência se a pessoa reproduzir.

## Critérios de aceite

- [x] Nenhuma requisição do RAGX ao Ollama usa o host `localhost` (teste que captura a URL das requisições do embedder e do `doctor`).
- [x] `base_url = "http://[::1]:11434"` explícito no `ragx.toml` continua valendo (quem tem Ollama só em IPv6 não perde a escolha).
- [x] Com Ollama real: `/api/tags` ≤ 50 ms e `embed_query` ≤ 100 ms (a auditoria mediu 6–12 ms e 23–44 ms).
- [x] Por chunk em batch 32 ≤ 15 ms (a auditoria mediu 9,8–12,3 ms).
- [x] Projeto antigo com `base_url = "http://localhost:11434"` no `ragx.toml` ganha a correção sem editar o arquivo.

## Medição

| Métrica | Antes | Depois |
|---|---|---|
| `GET /api/tags` | 2,05–2,1 s | 3–48 ms (3 ms em regime) |
| `POST /api/embed`, 1 texto | 2,06 s | 14 ms (a 1ª chamada, 1,4 s, é o modelo subindo na GPU) |
| Embedding por chunk, batch 32 | 87,5 ms | 6,8–7,2 ms |
| Embedding por chunk, batch 1 | 2.085 ms | 10–21 ms |

Comando (cada host 5 vezes, num script temporário fora do repo):

```python
import time, urllib.request as u
for h in ("localhost", "127.0.0.1") * 5:
    t = time.perf_counter()
    u.urlopen(f"http://{h}:11434/api/tags", timeout=10).read()
    print(h, round((time.perf_counter() - t) * 1000), "ms")
```

## Testes

- [x] `tests/unit/test_ollama_url.py` (novo): tabela de `resolve_base_url` (`http://localhost:11434`, `HTTP://LOCALHOST:11434/`, `localhost:11434`, `http://localhost.exemplo.com`, `http://127.0.0.1:11434`, `http://[::1]:11434`, `http://host:11434/api`). **Falha antes do conserto.**
- [x] `tests/unit/test_embeddings.py`: `OllamaEmbedder(base_url="http://localhost:11434").base_url == "http://127.0.0.1:11434"`; com `urllib.request.urlopen` espiado, `embed_query` e `available` batem em `127.0.0.1`.
- [x] `tests/unit/test_embedder_cache.py`: duas grafias da mesma URL compartilham a instância.
- [x] `tests/unit/test_doctor_ollama_processador.py`: a fixture usa `localhost` (linha 27); afirmar que `chamadas` contém só URLs em `127.0.0.1`.
- [x] Teste de config: `RAGX_EMBEDDING_BASE_URL` e `OLLAMA_HOST=localhost:11434` resultam em `http://127.0.0.1:11434`.

## Notas

- Confirmado em `config.py:62`, `ollama.py:28,36,81-86` e `doctor.py:168,196`. Este repositório usa `fastembed` (`ragx.toml`), então a própria suíte e o corpus do RAGX **não** reproduzem o ganho; quem sente é quem usa Ollama (esta máquina tem Ollama nativo na GPU).
- Não é um teste de arquivo nem de gate; nenhum byte do projeto passa a sair da máquina (continua loopback, ADR-0004). Por isso não há teste novo em `tests/security/`.
- `available()` tem `timeout=2` (`ollama.py:83`): com `localhost` ele estourava exatamente nesse limite. Não aumentar o timeout para "resolver".
- Se `127.0.0.1` falhar e `localhost` funcionar na máquina de alguém (Ollama só em IPv6), a mensagem de erro do `doctor` deve citar a URL efetiva e a chave `embedding.base_url`.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes (Windows rodado aqui; Linux e macOS pelo CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0132)` na branch `feat/v2`

## Andamento

2026-09-30. `resolve_base_url` ficou em `src/ragx/config.py` (e não em `embeddings/ollama.py`,
como a task sugeria) porque `config.py` não pode importar `ragx.embeddings` (ciclo); `ollama.py`
a reexporta. Ela roda como `field_validator` de `EmbeddingCfg.base_url`, então toml, `RAGX_EMBEDDING_BASE_URL`,
`OLLAMA_HOST`, o cache do embedder e o `doctor` recebem a URL já resolvida; o `doctor` também resolve
por conta própria (defensivo). Medido com o Ollama real desta máquina: ver a tabela de Medição.
Fast suite verde, `tests/security` verde, `ruff` e `mypy` limpos.
Pendência declarada na task e não feita aqui: o painel Electron (RAGX-0173).
