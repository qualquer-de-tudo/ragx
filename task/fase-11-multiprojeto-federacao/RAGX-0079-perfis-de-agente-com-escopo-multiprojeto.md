# RAGX-0079 — Perfis de agente com escopo multiprojeto

| | |
|---|---|
| **Fase** | 11 — Multiprojeto + Federação |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0078`, `RAGX-0051` |
| **Bloqueia** | `RAGX-0080` |
| **Documentação** | [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) · [10-agent-training.md](../../docs/10-agent-training.md) |
| **Status** | `todo` |

## Objetivo

Permitir um perfil de agente que trabalha sobre mais de um repositório — o caso do dev de integração entre microsserviços.

## Entregáveis

- [ ] `manifest.scope` aceita `projects: [...]` além de `include_paths`
- [ ] `ragx agent train` recorta o dicionário de workspace e inclui as integrações relevantes
- [ ] `instructions.md` orienta o uso de `scope` e de `get_contract`
- [ ] `ragx agent eval` com `expect_project` nos casos

## Fora de escopo

- Perfil compartilhado entre máquinas com registros diferentes

## Critérios de aceite

- [ ] Perfil multiprojeto compila e valida contra o schema
- [ ] Escopo com projeto não registrado falha com mensagem clara
- [ ] Avaliação verifica de qual projeto veio a fonte esperada

## Testes

- [ ] Perfil de exemplo sobre 2 projetos

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
