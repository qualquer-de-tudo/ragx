# RAGX-0045 — CLI do dicionário e serialização estável

| | |
|---|---|
| **Fase** | 5 — Knowledge Dictionary |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0043` |
| **Bloqueia** | `RAGX-0046`, `RAGX-0055`, `RAGX-0059` |
| **Documentação** | [08-dictionary.md](../../docs/08-dictionary.md) · [12-git-sync.md](../../docs/12-git-sync.md) |
| **Status** | `todo` |

## Objetivo

Gravar `knowledge/` de forma que o Git produza diff legível e merge viável.

## Entregáveis

- [ ] `ragx dictionary generate [--semantic] [--out DIR]`
- [ ] `ragx dictionary show [--section] [--json]`
- [ ] Serialização com `sort_keys=True`, `indent=2`, `ensure_ascii=False`, newline `\n`
- [ ] `generated_at` isolado, fora do hash de comparação

## Fora de escopo

- Serialização de documents/chunks (RAGX-0059)

## Critérios de aceite

- [ ] Regeneração sobre índice inalterado produz arquivo byte-idêntico (descontado `generated_at`)
- [ ] `--section` devolve só a seção pedida, em centenas de tokens
- [ ] Arquivo gerado no Windows e no Linux é idêntico (sem CRLF)

## Testes

- [ ] Teste de idempotência byte a byte
- [ ] Teste cross-platform no CI

## Notas

Porta de saída da Fase 5.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
