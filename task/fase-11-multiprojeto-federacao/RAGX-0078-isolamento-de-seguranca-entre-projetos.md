# RAGX-0078 — Isolamento de segurança entre projetos

| | |
|---|---|
| **Fase** | 11 — Multiprojeto + Federação |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0077` |
| **Bloqueia** | `RAGX-0079` |
| **Documentação** | [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) · [13-testes-hardening.md](../../docs/13-testes-hardening.md) |
| **Status** | `todo` |

## Objetivo

Provar que agregar N projetos não cria uma rota nova de vazamento.

## Entregáveis

- [ ] Superfícies `knowledge`, `federation` e `hub` acrescentadas à suíte das cinco (agora oito)
- [ ] Cenário com dois projetos registrados, um contendo a fixture de segredos
- [ ] Teste de que nenhuma consulta a partir do outro projeto, em nenhum `scope`, retorna algo da fixture
- [ ] Teste de `visibility = "private"` em todos os caminhos (CLI, MCP, hub dictionary, graph)
- [ ] Teste de que o re-scan na entrada do hub pega segredo que o ruleset de origem deixou passar
- [ ] Teste de que nenhum caminho absoluto atravessa projetos

## Fora de escopo

- Pentest externo

## Critérios de aceite

- [ ] Zero ocorrência de segredo em consulta cross-project, em qualquer `scope`
- [ ] Projeto `private` invisível em 100% dos caminhos testados
- [ ] Re-scan do hub bloqueia artefato que chegou com segredo
- [ ] Superfícies `knowledge`, `federation` e `hub` sem `xfail`

## Testes

- [ ] A própria suíte é o entregável

## Notas

Porta de saída da Fase 11. Com ela, a suíte de segurança cobre 8 superfícies.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
