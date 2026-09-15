# RAGX-0030 — CLI de busca

| | |
|---|---|
| **Fase** | 2 — Semantic + Hybrid Search |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0029` |
| **Bloqueia** | `RAGX-0031`, `RAGX-0038` |
| **Documentação** | [05-busca.md](../../docs/05-busca.md) · [14-cli.md](../../docs/14-cli.md) |
| **Status** | `todo` |

## Objetivo

Entregar o comando que fecha o MVP vertical.

## Entregáveis

- [ ] `ragx search "<query>"` com `--mode`, `--limit`, `--lang`, `--kind`, `--path`, `--min-score`, `--raw`, `--json`
- [ ] Saída Rich com posição, score, fonte, símbolo, `matched_by` e trecho
- [ ] Rodapé com tempo por etapa (semantic / keyword / fusion)
- [ ] Mensagem clara quando não há embeddings: busca continua em modo keyword

## Fora de escopo

- Contexto montado (Fase 4)

## Critérios de aceite

- [ ] Saída reproduz o formato do doc 05
- [ ] Todo resultado traz source, chunk, score e metadata — sem exceção
- [ ] `--json` estável
- [ ] Busca em índice de 10k chunks responde em menos de 300 ms

## Testes

- [ ] E2E `init → index → search`
- [ ] Snapshot da saída `--json`

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
