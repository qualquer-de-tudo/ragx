# RAGX-0111 — `get_dictionary` em níveis

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 5 — conhecimento hierárquico |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0110` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [09-mcp.md](../../docs/09-mcp.md) · [08-dictionary.md](../../docs/08-dictionary.md) |
| **Status** | `done` |

## Objetivo

O agente deve poder começar barato e aprofundar — hoje ele paga o dicionário inteiro ou nada. É o Nível 0/1/2 do conhecimento hierárquico, e a estrutura para isso já existe.

## Entregáveis

- [x] `get_dictionary(level=0)` — projeto, tecnologias, pontos de entrada (~800 tokens)
- [x] `get_dictionary(level=1)` — módulos com resumo (~2.000 tokens)
- [x] `get_dictionary(level=2)` — o conteúdo completo
- [x] `section` continua funcionando, combinável com `level`
- [x] O playbook passa a recomendar `level=0` como primeira chamada
- [x] A descrição da ferramenta MCP diz o custo em tokens de cada nível

## Fora de escopo

- Mudar o formato de `knowledge/dictionary.json` em disco — os níveis são recorte de leitura

## Critérios de aceite

- [x] `level=0` abaixo de 1.000 tokens
- [x] Cada nível é superconjunto do anterior
- [x] `docs/09-mcp.md` documenta os três níveis (há teste que compara ferramentas registradas com documentadas)

## Testes

- [x] Teste do teto de tokens por nível
- [x] Teste de que `level=2` equivale ao comportamento atual

## Notas

Fecha o §15 do pedido de auditoria: *retrieve progressively, do not retrieve everything*.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação confere com o comportamento implementado

## Andamento

- 2026-10-02 — `builder.at_level` + `LEVELS`; `get_dictionary(section?, level=2)` no MCP (nível inválido vira `invalid_argument`); `ragx dictionary show --level`; playbook, `instructions` do servidor e perfil de agente passam a pedir `level=0`; descrição da ferramenta diz o custo de cada nível; arquivos-ouro de `tools/list` regravados (descrição e `level` no schema, de propósito). **Medido: nível 0 = 411 tokens, nível 1 = 1.669, nível 2 = 3.701** (meta do 0: < 1.000). Cada nível é superconjunto do anterior (teste por campo e por item). `section` + `level` combinam.
