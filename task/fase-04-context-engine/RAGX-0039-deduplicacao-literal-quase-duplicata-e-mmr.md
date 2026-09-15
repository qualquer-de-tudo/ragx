# RAGX-0039 — Deduplicação: literal, quase-duplicata e MMR

| | |
|---|---|
| **Fase** | 4 — Context Engine |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0038` |
| **Bloqueia** | `RAGX-0040` |
| **Documentação** | [07-context-engine.md](../../docs/07-context-engine.md) |
| **Status** | `todo` |

## Objetivo

Eliminar repetição e garantir cobertura, em vez de dez variações do mesmo trecho.

## Entregáveis

- [ ] `context/dedup.py`: duplicata literal por `content_hash`
- [ ] Quase-duplicata por cosseno acima de `dedup_threshold` (0.93), reaproveitando vetores já gravados
- [ ] MMR com `lambda` configurável (padrão 0.7)
- [ ] Registro do que foi descartado e por quê, para o `--explain`

## Fora de escopo

- Compressão (RAGX-0040)

## Critérios de aceite

- [ ] Nenhuma duplicata literal no pack (teste: `content_hash` único entre fragmentos)
- [ ] Código copiado em dois arquivos aparece uma vez, mantendo o de maior score
- [ ] MMR com `lambda = 0.5` aumenta mensuravelmente a diversidade de fontes
- [ ] Dedup de 100 candidatos em menos de 20 ms

## Testes

- [ ] Unitário do MMR com vetores conhecidos
- [ ] Fixture com duplicata real

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
