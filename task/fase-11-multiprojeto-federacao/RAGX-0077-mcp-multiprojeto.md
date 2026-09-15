# RAGX-0077 — MCP multiprojeto

| | |
|---|---|
| **Fase** | 11 — Multiprojeto + Federação |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0076`, `RAGX-0049` |
| **Bloqueia** | `RAGX-0078` |
| **Documentação** | [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `todo` |

## Objetivo

Dar ao agente acesso ao conhecimento cross-project sem afrouxar nenhuma fronteira.

## Entregáveis

- [ ] Parâmetro `scope` em `search_knowledge`, `search_hybrid`, `search_graph`, `build_context`, `get_dictionary`
- [ ] `list_projects`: projetos, estado (clonado/federação), degradações e integrações
- [ ] `get_contract`: contrato de um endpoint ou evento, com o projeto que o provê
- [ ] `project` obrigatório em todo item de resposta
- [ ] Descrições das ferramentas ensinando a começar por `list_projects` em ambiente multirrepositório
- [ ] Teste arquitetural continua valendo: nada de filesystem em `ragx.mcp`

## Fora de escopo

- Ferramenta de indexação cross-project

## Critérios de aceite

- [ ] Agente externo resolve uma integração entre dois projetos usando só MCP
- [ ] Projeto `private` invisível a qualquer `scope`
- [ ] `get_contract` funciona para projeto não clonado
- [ ] Teste arquitetural de imports continua verde
- [ ] `scope` inválido produz erro de validação, não busca silenciosa em tudo

## Testes

- [ ] Contrato das 2 ferramentas novas
- [ ] Comparação CLI × MCP em `--scope all`

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
