# RAGX-0025 — Provider Ollama (nomic-embed-text)

| | |
|---|---|
| **Fase** | 2 — Semantic + Hybrid Search |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0024` |
| **Bloqueia** | `RAGX-0027` |
| **Documentação** | [adr/ADR-0004-embeddings.md](../../docs/adr/ADR-0004-embeddings.md) · [15-configuracao.md](../../docs/15-configuracao.md) |
| **Status** | `todo` |

## Objetivo

Gerar embeddings localmente, sem que conteúdo do projeto saia da máquina.

## Entregáveis

- [ ] `embeddings/ollama.py` com batch de 32 e retry exponencial
- [ ] Prefixos obrigatórios `search_document: ` e `search_query: ` aplicados pelo provider
- [ ] `ragx index --embed-only` para completar vetores faltantes
- [ ] Degradação explícita: embedder fora do ar grava chunks sem vetor e avisa, sem derrubar a indexação
- [ ] `ragx doctor` checa conectividade e presença do modelo

## Fora de escopo

- Providers remotos pagos — opt-in, fora do MVP

## Critérios de aceite

- [ ] Prefixos aplicados nos dois métodos, comprovado por teste com cliente fake
- [ ] Embedder indisponível → indexação conclui, busca cai para keyword, aviso claro
- [ ] Retry não duplica chunk nem vetor
- [ ] `--embed-only` preenche exatamente os faltantes

## Testes

- [ ] Cliente HTTP fake
- [ ] Teste de degradação com serviço fora do ar

## Notas

Modelo já disponível em `E:\RAGPAG\ragpag\ollama_models` — configurar `OLLAMA_MODELS` e subir `ollama serve` para o ambiente de desenvolvimento.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
