# RAGX-0058 — CLI de portabilidade

| | |
|---|---|
| **Fase** | 8 — Export / Import (.rag) |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,25d |
| **Depende de** | `RAGX-0057` |
| **Bloqueia** | — |
| **Documentação** | [14-cli.md](../../docs/14-cli.md) |
| **Status** | `todo` |

## Objetivo

Expor export, import e inspect com saída clara.

## Entregáveis

- [ ] `ragx export <arquivo.rag> [--include-embeddings] [--include-agents] [--scope]`
- [ ] `ragx import <arquivo.rag> [--replace|--merge] [--skip-embeddings]`
- [ ] `ragx inspect <arquivo.rag> [--json]`
- [ ] Relatório de import com o que foi aplicado, ignorado e por quê

## Critérios de aceite

- [ ] E2E export → import em diretório limpo funciona seguindo só a documentação
- [ ] Aviso de incompatibilidade é claro e acionável

## Testes

- [ ] E2E completo de portabilidade

## Notas

Porta de saída da Fase 8.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
