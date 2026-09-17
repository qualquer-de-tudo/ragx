# RAGX-0111 — `get_dictionary` em níveis

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 5 — conhecimento hierárquico |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0110` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [09-mcp.md](../../docs/09-mcp.md) · [08-dictionary.md](../../docs/08-dictionary.md) |
| **Status** | `todo` |

## Objetivo

O agente deve poder começar barato e aprofundar — hoje ele paga o dicionário inteiro ou nada. É o Nível 0/1/2 do conhecimento hierárquico, e a estrutura para isso já existe.

## Entregáveis

- [ ] `get_dictionary(level=0)` — projeto, tecnologias, pontos de entrada (~800 tokens)
- [ ] `get_dictionary(level=1)` — módulos com resumo (~2.000 tokens)
- [ ] `get_dictionary(level=2)` — o conteúdo completo
- [ ] `section` continua funcionando, combinável com `level`
- [ ] O playbook passa a recomendar `level=0` como primeira chamada
- [ ] A descrição da ferramenta MCP diz o custo em tokens de cada nível

## Fora de escopo

- Mudar o formato de `knowledge/dictionary.json` em disco — os níveis são recorte de leitura

## Critérios de aceite

- [ ] `level=0` abaixo de 1.000 tokens
- [ ] Cada nível é superconjunto do anterior
- [ ] `docs/09-mcp.md` documenta os três níveis (há teste que compara ferramentas registradas com documentadas)

## Testes

- [ ] Teste do teto de tokens por nível
- [ ] Teste de que `level=2` equivale ao comportamento atual

## Notas

Fecha o §15 do pedido de auditoria: *retrieve progressively, do not retrieve everything*.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
