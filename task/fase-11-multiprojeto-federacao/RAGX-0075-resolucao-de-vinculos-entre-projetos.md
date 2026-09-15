# RAGX-0075 — Resolução de vínculos entre projetos

| | |
|---|---|
| **Fase** | 11 — Multiprojeto + Federação |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0074` |
| **Bloqueia** | `RAGX-0076` |
| **Documentação** | [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) · [adr/ADR-0011-federacao-entre-projetos.md](../../docs/adr/ADR-0011-federacao-entre-projetos.md) |
| **Status** | `todo` |

## Objetivo

Cruzar o que cada projeto consome com o que os outros provêem, e reportar com honestidade o que não fechou.

## Entregáveis

- [ ] `federation/linker.py` cruzando `consumes` × `provides` por `kind` + `normalized`
- [ ] Escala de confiança do doc 17 (contrato 1.0 · método+rota 0.95 · rota com método divergente 0.6 · nome 0.8 · similaridade 0.4 vira sugestão)
- [ ] Gravação em `cross_links`; não resolvidos e divergências em `unresolved`
- [ ] `ragx hub link` com a saída de três blocos: resolvidos, sem provedor, divergências
- [ ] `ragx hub dictionary`: dicionário de workspace com `integrations`, `unresolved_consumes` e `divergences`
- [ ] `[federation] min_confidence` respeitado

## Fora de escopo

- Correção automática de divergência — o RAGX reporta, quem corrige é o time

## Critérios de aceite

- [ ] 3 projetos registrados têm seus vínculos HTTP e de eventos resolvidos
- [ ] Consumo sem provedor conhecido é listado, não silenciado
- [ ] Divergência de método (`PUT` consumido × `POST` provido) é reportada como possível bug de integração
- [ ] Vínculo abaixo de `min_confidence` vira sugestão, não aresta
- [ ] Resolução é idempotente e roda em menos de 2 s para 10 projetos

## Testes

- [ ] Cenário com vínculo exato, divergente e não resolvido
- [ ] Normalização entre stacks distintas

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
