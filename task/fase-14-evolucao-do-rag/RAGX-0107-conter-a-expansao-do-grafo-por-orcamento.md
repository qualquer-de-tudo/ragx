# RAGX-0107 — Conter a expansão do grafo por orçamento

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 4 — recuperação adaptativa |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [06-grafo.md](../../docs/06-grafo.md) |
| **Status** | `todo` |

## Objetivo

Medido numa pergunta única: `graph_seeds: 209`, `graph_nodes: 209`. A expansão trouxe 209 nós, que viraram 50 candidatos e 22 fragmentos de ~136 tokens cada. Contexto picado em 22 pedaços de duas linhas, vindo de ~15 arquivos, é caro de ler e fácil de interpretar mal.

## Entregáveis

- [ ] A expansão respeita um orçamento de CONTEXTO, não só `max_nodes`
- [ ] Teto de fragmentos por pacote, com mínimo de tokens por fragmento — fragmento de 30 tokens raramente informa
- [ ] Fragmentos vizinhos do mesmo arquivo são unidos antes de contar como dois
- [ ] `--explain` mostra quantos nós a expansão trouxe e quantos sobreviveram

## Fora de escopo

- Desligar a expansão por grafo — ela é útil; o que falta é freio

## Critérios de aceite

- [ ] A mesma consulta produz um pacote com menos fragmentos e mais tokens úteis por fragmento
- [ ] `estimated_tokens` continua abaixo do orçamento
- [ ] recall@5 não piora no conjunto ampliado

## Testes

- [ ] Teste de que fragmentos adjacentes do mesmo arquivo são unidos
- [ ] Teste do teto de fragmentos

## Notas

Relacionado à `RAGX-0097`: parte dos 6,7 s de `build_context` medidos vem de expandir 209 nós e depois descartar quase tudo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
