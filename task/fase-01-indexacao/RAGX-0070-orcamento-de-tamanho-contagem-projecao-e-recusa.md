# RAGX-0070 — Orçamento de tamanho: contagem, projeção e recusa

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0014` |
| **Bloqueia** | `RAGX-0071`, `RAGX-0059` |
| **Documentação** | [16-orcamento-de-tamanho.md](../../docs/16-orcamento-de-tamanho.md) |
| **Status** | `todo` |

## Objetivo

Tornar o teto do Git uma restrição que o sistema faz cumprir, em vez de um limite que alguém descobre quando o push é rejeitado.

## Entregáveis

- [ ] `sizing/budget.py`: contagem por categoria e projeção antes de gravar
- [ ] Seção `[size]` em `ragx.toml` com `max_artifact_bytes`, `warn_total_bytes`, `fail_total_bytes`, `max_chunks`, `shards`
- [ ] **Recusa de escrita** ao projetar estouro de `fail_total_bytes` — nunca truncamento silencioso
- [ ] Mensagem acionável: maiores contribuintes + 3 sugestões (ignore, reduzir `versioned_dim`, elevar o teto)
- [ ] Aviso ao passar de `warn_total_bytes`
- [ ] `ragx size` com `--check`, `--projection`, `--history`, `--json`
- [ ] `sizing/sharding.py`: shard por prefixo de ID, com rebalanceamento 16 → 32
- [ ] `ragx status` e `ragx doctor` exibem a barra de orçamento

## Fora de escopo

- Gravação de `knowledge/` propriamente dita (RAGX-0059)

## Critérios de aceite

- [ ] Projeção de estouro recusa a gravação (exit 1) e não escreve nada
- [ ] `--check` serve em CI e retorna exit 1 ao estourar
- [ ] `--history` mostra o crescimento de `knowledge/` nos últimos N commits
- [ ] Sharding por prefixo mantém 15 de 16 shards byte-idênticos quando 1 chunk muda
- [ ] Rebalanceamento dispara e é registrado no `manifest.json` dos embeddings
- [ ] Contagem bate com o tamanho real em disco (tolerância 2%)

## Testes

- [ ] Repositório sintético que estoura o teto
- [ ] Teste de estabilidade de shard
- [ ] Teste de rebalanceamento

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
