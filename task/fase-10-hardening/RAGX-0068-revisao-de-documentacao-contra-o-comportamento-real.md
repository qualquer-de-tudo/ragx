# RAGX-0068 — Revisão de documentação contra o comportamento real

| | |
|---|---|
| **Fase** | 10 — Hardening + Release |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0067` |
| **Bloqueia** | — |
| **Documentação** | [README.md](../../docs/README.md) |
| **Status** | `todo` |

## Objetivo

Eliminar divergência entre o que a documentação promete e o que o código faz — documentação divergente é dívida, não referência.

## Entregáveis

- [ ] Revisão dos 18 documentos de `docs/` contra o comportamento implementado
- [ ] Atualização de todas as saídas de exemplo da CLI com saídas reais
- [ ] Registro de decisões que mudaram durante a implementação, como ADR novo ou como `substituído por`
- [ ] Confirmação de que todos os critérios de aceite documentados são efetivamente verificados por teste

## Fora de escopo

- Reescrita da documentação

## Critérios de aceite

- [ ] Nenhum comando documentado que não exista; nenhum comando existente não documentado
- [ ] Toda saída de exemplo corresponde à saída real
- [ ] Todo critério de aceite dos docs tem teste correspondente, ou está marcado explicitamente como não verificado automaticamente
- [ ] Zero `xfail` restante na suíte de segurança

## Testes

- [ ] Teste que extrai comandos dos docs e confere contra `ragx --help` recursivo

## Notas

Porta de saída da Fase 10 e do MVP.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
