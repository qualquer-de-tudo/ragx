# RAGX-0076 — Busca e contexto cross-project

| | |
|---|---|
| **Fase** | 11 — Multiprojeto + Federação |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0075`, `RAGX-0041` |
| **Bloqueia** | `RAGX-0077` |
| **Documentação** | [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) · [05-busca.md](../../docs/05-busca.md) · [07-context-engine.md](../../docs/07-context-engine.md) |
| **Status** | `todo` |

## Objetivo

Responder, de dentro de um projeto, perguntas cuja resposta está em outro — inclusive quando esse outro não está clonado.

## Entregáveis

- [ ] `--scope current|all|project:<nome>` em `ragx search`, `ragx context` e `ragx graph-search`
- [ ] Leque: projeto atual (completo) + projetos clonados (`.ragx/knowledge.db` de cada um) + só-federação (fatia pública)
- [ ] Fusão RRF com `hub.external_penalty` (0,85) para projeto externo
- [ ] `project` obrigatório em todo resultado e em todo fragmento de contexto
- [ ] Projeto com modelo de embedding divergente participa só por keyword + federação, com aviso
- [ ] `ragx hub graph <projeto> [--depth]` mostrando integrações

## Fora de escopo

- Cache cross-project — avaliar depois de medir

## Critérios de aceite

- [ ] `ragx search "criar pagamento" --scope all` de dentro de `order-service` devolve o contrato de `payment-service`
- [ ] Funciona com `payment-service` **não clonado**, usando só a fatia
- [ ] Nenhum resultado sem `project` preenchido
- [ ] Projeto `private` não aparece em nenhum `scope`, nem em `project:<nome>` explícito
- [ ] `--scope all` com 5 projetos responde em menos de 800 ms
- [ ] Modelo divergente degrada para keyword com aviso, sem ranking falso

## Testes

- [ ] Cenário de 3 projetos, um não clonado
- [ ] Teste de degradação por modelo divergente

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
