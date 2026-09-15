# RAGX-0042 — CLI ragx context com --explain

| | |
|---|---|
| **Fase** | 4 — Context Engine |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0041` |
| **Bloqueia** | `RAGX-0046` |
| **Documentação** | [07-context-engine.md](../../docs/07-context-engine.md) · [14-cli.md](../../docs/14-cli.md) |
| **Status** | `todo` |

## Objetivo

Entregar o contexto pronto para uso e tornar a decisão do engine auditável.

## Entregáveis

- [ ] `ragx context "<query>"` com `--tokens`, `--format markdown|json|xml`, `--include-graph`, `--depth`, `--out`
- [ ] Saída Markdown no formato do doc 07, com rodapé de contagem
- [ ] `--explain`: intenção detectada, por que cada fragmento entrou e por que cada descartado saiu

## Fora de escopo

- Exposição via MCP (RAGX-0047)

## Critérios de aceite

- [ ] Saída reproduz o formato do doc 07
- [ ] `--explain` justifica 100% dos fragmentos incluídos e descartados
- [ ] `--format json` serializa o `ContextPack` completo
- [ ] `--out` grava sem códigos de cor ANSI

## Testes

- [ ] E2E `index → context`
- [ ] Snapshot das três formatações

## Notas

Porta de saída da Fase 4.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
