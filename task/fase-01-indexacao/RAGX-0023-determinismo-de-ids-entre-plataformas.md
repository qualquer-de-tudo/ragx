# RAGX-0023 — Determinismo de IDs entre plataformas

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0021`, `RAGX-0011` |
| **Bloqueia** | — |
| **Documentação** | [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) · [13-testes-hardening.md](../../docs/13-testes-hardening.md) |
| **Status** | `todo` |

## Objetivo

Provar, em CI, que o índice gerado no Windows e no Linux é idêntico — requisito do merge no Git da Fase 9.

## Entregáveis

- [ ] Snapshot de IDs de chunk commitado, gerado a partir de uma fixture fixa
- [ ] Teste comparando o snapshot nos dois SOs do CI
- [ ] Documentação do procedimento de regeneração do snapshot ao bumpar `CHUNKER_VERSION`

## Fora de escopo

- Serialização de `knowledge/` (RAGX-0059)

## Critérios de aceite

- [ ] IDs idênticos em ubuntu-latest e windows-latest
- [ ] Divergência falha o build com diff legível apontando o chunk
- [ ] Bump de `CHUNKER_VERSION` exige regeneração explícita e revisada do snapshot

## Testes

- [ ] O próprio teste de snapshot

## Notas

Porta de saída da Fase 1, junto com RAGX-0021.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
